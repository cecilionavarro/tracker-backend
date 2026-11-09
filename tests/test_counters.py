import asyncio
import importlib
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.session_update_request import SessionUpdateRequest

USER_ID = ObjectId()
# 21:00 UTC is 14:00 on Friday, September 11, in Los Angeles.
NOW = datetime(2026, 9, 11, 21, tzinfo=timezone.utc)
# Midnight at the start of that Friday in Los Angeles.
LA_MIDNIGHT = datetime(2026, 9, 11, 7, tzinfo=timezone.utc)


def load_modules():
    # Import against fake collections and a fake gpiozero, so these tests
    # never reach MongoDB or the Pi's pins.
    database = ModuleType("app.core.database")
    for name in ("sessions_collection", "events_collection", "categories_collection", "pullups_collection",
                 "notes_collection", "buttons_collection"):
        setattr(database, name, MagicMock())
    config = ModuleType("app.core.config")
    config.settings = SimpleNamespace(SESSION_CATEGORY="CREATING")
    gpiozero = ModuleType("gpiozero")
    gpiozero.LED = MagicMock()
    gpiozero.Button = MagicMock(side_effect=lambda *args, **kwargs: MagicMock(pin=args[0], kwargs=kwargs))
    fakes = {"app.core.database": database, "app.core.config": config, "gpiozero": gpiozero}
    names = ("app.services.overview_service", "app.services.pullup_service", "app.services.session_service",
             "app.services.state_manager", "app.hardware.gpio_handler", "app.api.v1.endpoints.counters",
             "app.api.v1.endpoints.clock")
    with patch.dict(sys.modules, fakes):
        for name in names:
            sys.modules.pop(name, None)
        modules = SimpleNamespace(**{name.rsplit(".", 1)[1]: importlib.import_module(name) for name in names})
    return database, gpiozero, modules


class CounterTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db, self.gpiozero, self.m = load_modules()
        self.db.events_collection.insert_one = AsyncMock()
        for module in (self.m.session_service, self.m.pullup_service, self.m.overview_service):
            clock = patch.object(module, "datetime")
            fake = clock.start()
            fake.now.return_value = NOW
            fake.combine = datetime.combine
            self.addCleanup(clock.stop)


class DistractionTests(CounterTestCase):
    async def test_press_adds_one_to_the_running_session_atomically(self):
        session_id = ObjectId()
        self.db.sessions_collection.find_one_and_update = AsyncMock(
            return_value={"_id": session_id, "distractions": 3})

        result = await self.m.session_service.session_service.change_distractions(str(USER_ID), 1, "raspberry_pi")

        self.assertEqual(result, {"session_id": str(session_id), "distractions": 3})
        query, update = self.db.sessions_collection.find_one_and_update.await_args.args
        self.assertEqual(query, {"user_id": USER_ID, "status": "active", "end_time": None})
        self.assertEqual(update, {"$inc": {"distractions": 1}, "$set": {"updated_at": NOW}})
        event = self.db.events_collection.insert_one.await_args.args[0]
        self.assertEqual((event["session_id"], event["event_type"], event["source"]),
                         (str(session_id), "distraction", "raspberry_pi"))

    async def test_press_without_a_running_session_counts_nothing(self):
        self.db.sessions_collection.find_one_and_update = AsyncMock(return_value=None)
        service = self.m.session_service.session_service

        self.assertIsNone(await service.change_distractions(str(USER_ID), 1, "raspberry_pi"))
        self.db.events_collection.insert_one.assert_not_awaited()

    async def test_removing_never_goes_below_zero(self):
        session_id = ObjectId()
        service = self.m.session_service.session_service
        self.db.sessions_collection.find_one_and_update = AsyncMock(return_value=None)
        self.db.sessions_collection.find_one = AsyncMock(return_value={"_id": session_id})

        result = await service.change_distractions(str(USER_ID), -1, "api")

        query, update = self.db.sessions_collection.find_one_and_update.await_args.args
        self.assertEqual(query["distractions"], {"$gte": 1})
        self.assertEqual(update["$inc"], {"distractions": -1})
        self.assertEqual(result, {"session_id": str(session_id), "distractions": 0})
        self.db.events_collection.insert_one.assert_not_awaited()

        self.db.sessions_collection.find_one = AsyncMock(return_value=None)
        self.assertIsNone(await service.change_distractions(str(USER_ID), -1, "api"))

    async def test_session_edit_can_correct_the_count(self):
        doc = {"_id": ObjectId(), "user_id": USER_ID, "category_id": ObjectId(), "status": "completed",
               "start_time": NOW - timedelta(hours=2), "end_time": NOW - timedelta(hours=1),
               "elapsed_time": 3600, "distractions": 5, "updated_at": NOW - timedelta(hours=1)}
        self.db.sessions_collection.find_one = AsyncMock(return_value=doc)
        self.db.sessions_collection.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
        self.db.categories_collection.find_one = AsyncMock(return_value=None)

        result = await self.m.session_service.session_service.update_session(
            str(USER_ID), str(doc["_id"]), {"distractions": 2})

        _, update = self.db.sessions_collection.update_one.await_args.args
        self.assertEqual(update["$set"]["distractions"], 2)
        self.assertNotIn("elapsed_time", update["$set"])
        self.assertEqual(result["distractions"], 2)

    def test_edit_request_rejects_negative_counts(self):
        with self.assertRaises(ValidationError):
            SessionUpdateRequest(distractions=-1)
        self.assertEqual(SessionUpdateRequest(distractions=0).distractions, 0)


class PullupTests(CounterTestCase):
    async def test_press_saves_one_pullup_and_counts_today_in_los_angeles(self):
        self.db.pullups_collection.insert_one = AsyncMock()
        self.db.pullups_collection.count_documents = AsyncMock(return_value=12)

        today = await self.m.pullup_service.pullup_service.add_pullup(str(USER_ID), "raspberry_pi")

        self.assertEqual(today, 12)
        saved = self.db.pullups_collection.insert_one.await_args.args[0]
        self.assertEqual(saved, {"user_id": USER_ID, "source": "raspberry_pi", "created_at": NOW})
        query = self.db.pullups_collection.count_documents.await_args.args[0]
        self.assertEqual(query, {"user_id": USER_ID, "created_at": {"$gte": LA_MIDNIGHT}})

    async def test_undo_removes_todays_latest_pullup_only(self):
        service = self.m.pullup_service.pullup_service
        self.db.pullups_collection.find_one_and_delete = AsyncMock(return_value={"_id": ObjectId()})
        self.db.pullups_collection.count_documents = AsyncMock(return_value=11)

        self.assertEqual(await service.remove_last_pullup(str(USER_ID)), 11)
        call = self.db.pullups_collection.find_one_and_delete.await_args
        self.assertEqual(call.args[0], {"user_id": USER_ID, "created_at": {"$gte": LA_MIDNIGHT}})
        self.assertEqual(call.kwargs["sort"], [("created_at", -1)])

        self.db.pullups_collection.find_one_and_delete = AsyncMock(return_value=None)
        self.assertIsNone(await service.remove_last_pullup(str(USER_ID)))


class PullupStatsTests(CounterTestCase):
    def test_sets_split_on_rests_longer_than_a_minute(self):
        split = self.m.pullup_service.split_into_sets
        start = NOW - timedelta(hours=1)
        # 4 taps a second apart, a 10-second rest, 3 taps 3 seconds apart, then
        # a tap 4 seconds later.
        times = [start + timedelta(seconds=offset) for offset in (0, 1, 2, 3, 13, 16, 19, 23)]
        self.assertEqual(split(times), [4, 3, 1])
        self.assertEqual(split([]), [])

    def test_streak_survives_until_today_ends(self):
        streak = self.m.pullup_service.get_streak_days
        today = date(2026, 9, 11)
        days = {today - timedelta(days=offset) for offset in (1, 2, 3, 5)}
        self.assertEqual(streak(days, today), 3)
        self.assertEqual(streak(days | {today}, today), 4)
        self.assertEqual(streak(set(), today), 0)

    async def test_stats_cover_today_this_week_and_all_time(self):
        def at(day, hour, minute=0, second=0):
            # Times in Los Angeles, which is UTC-7 in September.
            return datetime(2026, 9, day, hour + 7, minute, second, tzinfo=timezone.utc)

        times = [
            # Last week: Thursday the 3rd and Saturday the 5th.
            at(3, 9), at(3, 9, 0, 4), at(5, 9),
            # This week: Wednesday the 9th, then today, Friday the 11th, before 2 PM.
            at(9, 8), at(9, 8, 0, 3), at(9, 8, 0, 6), at(9, 8, 0, 9),
            at(11, 7), at(11, 7, 0, 3), at(11, 7, 5), at(11, 7, 5, 2), at(11, 7, 5, 4),
        ]
        self.db.pullups_collection.find.return_value.sort.return_value.to_list = AsyncMock(
            return_value=[{"created_at": moment} for moment in times])
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[
            {"_id": "2026-08-20", "count": 9}, {"_id": "2026-09-03", "count": 2},
            {"_id": "2026-09-05", "count": 1}, {"_id": "2026-09-09", "count": 4},
            {"_id": "2026-09-10", "count": 1}, {"_id": "2026-09-11", "count": 5},
        ])
        self.db.pullups_collection.aggregate = AsyncMock(return_value=cursor)

        stats = await self.m.pullup_service.pullup_service.get_stats(str(USER_ID))

        self.assertEqual(stats["today"], {"count": 5, "sets": 2, "best_set": 3, "last_at": at(11, 7, 5, 4)})
        self.assertEqual(stats["week"], {
            "count": 9, "daily_average": 1.8, "best_set": 4,
            # Last week through Friday 2 PM: only Thursday's 2 count.
            "last_week_to_date": 2, "last_week_total": 3,
        })
        self.assertEqual(stats["all_time"], {
            "count": 22, "active_days": 6, "streak_days": 3,
            "best_day": {"date": "2026-08-20", "count": 9}, "first_day": "2026-08-20",
        })
        # Today's second set: 3 taps ending at 7:05:04.
        self.assertEqual(stats["last_set"], {"count": 3, "at": at(11, 7, 5, 4)})
        query = self.db.pullups_collection.find.call_args.args[0]
        # From Monday the 31st of August, the start of last week.
        self.assertEqual(query["created_at"], {"$gte": datetime(2026, 8, 31, 7, tzinfo=timezone.utc)})
        group = self.db.pullups_collection.aggregate.await_args.args[0][1]["$group"]
        self.assertEqual(group["_id"]["$dateToString"]["timezone"], "America/Los_Angeles")

    async def test_last_set_reaches_past_two_weeks(self):
        latest = datetime(2026, 8, 1, 16, tzinfo=timezone.utc)
        taps = [latest - timedelta(seconds=offset) for offset in (40, 2, 0)]
        self.db.pullups_collection.find.return_value.sort.return_value.to_list = AsyncMock(
            side_effect=[[], [{"created_at": moment} for moment in taps]])
        self.db.pullups_collection.find_one = AsyncMock(return_value={"created_at": latest})
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[{"_id": "2026-08-01", "count": 3}])
        self.db.pullups_collection.aggregate = AsyncMock(return_value=cursor)

        stats = await self.m.pullup_service.pullup_service.get_stats(str(USER_ID))

        self.assertEqual(stats["last_set"], {"count": 2, "at": latest})


class ActivityPullupTests(unittest.IsolatedAsyncioTestCase):
    async def test_activity_points_carry_each_days_pullups(self):
        database = ModuleType("app.core.database")
        for name in ("sessions_collection", "events_collection", "categories_collection", "pullups_collection",
                 "notes_collection", "buttons_collection"):
            setattr(database, name, MagicMock())
        config = ModuleType("app.core.config")
        config.settings = SimpleNamespace(SESSION_CATEGORY="CREATING")
        with patch.dict(sys.modules, {"app.core.database": database, "app.core.config": config}):
            for name in ("app.services.dashboard_activity_service", "app.services.session_service"):
                sys.modules.pop(name, None)
            module = importlib.import_module("app.services.dashboard_activity_service")
        database.sessions_collection.find.return_value.to_list = AsyncMock(return_value=[])
        database.categories_collection.find.return_value.to_list = AsyncMock(return_value=[])
        def tap(day, *offsets):
            # Taps on a day at 9 AM Los Angeles time, offsets in seconds.
            return [{"created_at": datetime(2026, 9, day, 16, tzinfo=timezone.utc) + timedelta(seconds=offset)}
                    for offset in offsets]
        database.pullups_collection.find.return_value.sort.return_value.to_list = AsyncMock(
            return_value=tap(10, 0, 1, 2, 20, 21) + tap(11, 0, 1, 2, 3, 4, 5, 6))

        with patch.object(module, "datetime") as clock:
            clock.now.return_value = NOW
            result = await module.DashboardActivityService().get_activity(str(USER_ID), 3)

        self.assertEqual(
            [(point["date"], point["pullups"], point["pullup_sets"], point["pullup_best_set"]) for point in result["points"]],
            [("2026-09-09", 0, 0, 0), ("2026-09-10", 5, 2, 3), ("2026-09-11", 7, 1, 7)])
        match = database.pullups_collection.find.call_args.args[0]
        # From midnight Wednesday the 9th in Los Angeles to midnight Saturday.
        self.assertEqual(match["created_at"], {
            "$gte": datetime(2026, 9, 9, 7, tzinfo=timezone.utc),
            "$lt": datetime(2026, 9, 12, 7, tzinfo=timezone.utc),
        })


class StateAndEndpointTests(CounterTestCase):
    def manager(self):
        self.loop = MagicMock()
        return self.m.state_manager.StateManager(self.loop, USER_ID)

    async def test_counts_broadcast_to_dashboards_only_when_they_change(self):
        manager = self.manager()
        with patch.object(self.m.state_manager.pullup_service, "add_pullup", AsyncMock(return_value=4)):
            self.assertEqual(await manager.record_pullup(), 4)
        self.loop.call_soon_threadsafe.assert_called_once()

        with patch.object(self.m.state_manager.session_service, "change_distractions",
                          AsyncMock(return_value=None)):
            self.assertIsNone(await manager.record_distraction())
        self.loop.call_soon_threadsafe.assert_called_once()

    async def test_the_dashboard_switches_activities_without_toggling_off(self):
        manager = self.manager()
        manager.clock_in = AsyncMock(side_effect=lambda category, tags: setattr(manager, "clocked_in", True))
        manager.clock_out = AsyncMock(side_effect=lambda: setattr(manager, "clocked_in", False))
        manager.is_active_session = MagicMock(return_value=False)

        await manager.clock_into("c1", "deep_work")
        manager.clock_in.assert_awaited_once_with(category="c1", tags="deep_work")
        manager.clock_out.assert_not_awaited()

        # Switching clocks out of the running one first.
        await manager.clock_into("c2")
        manager.clock_out.assert_awaited_once()
        self.assertEqual(manager.clock_in.await_count, 2)

        # Picking the running one again leaves it running.
        manager.is_active_session.return_value = True
        await manager.clock_into("c2")
        self.assertEqual((manager.clock_in.await_count, manager.clock_out.await_count), (2, 1))

        self.assertTrue(await manager.clock_out_if_running())
        self.assertFalse(await manager.clock_out_if_running())

    async def test_clock_endpoints_check_the_category_and_sync_the_led(self):
        clock = self.m.clock
        state_manager = SimpleNamespace(
            clock_into=AsyncMock(), clock_out_if_running=AsyncMock(return_value=False),
            get_state=MagicMock(return_value={"clocked_in": True, "started_at": None, "category_id": "c1", "tags": ""}),
        )
        gpio = SimpleNamespace(sync_led=MagicMock())
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(state_manager=state_manager, gpio=gpio)))
        category_id = ObjectId()

        self.db.categories_collection.find_one = AsyncMock(return_value={"_id": category_id, "label": "Reading"})
        result = await clock.clock_in(request, clock.ClockInRequest(category_id=str(category_id), tags="deep_work"))
        self.assertTrue(result["clocked_in"])
        state_manager.clock_into.assert_awaited_once_with(str(category_id), "deep_work")
        gpio.sync_led.assert_called_once()

        self.db.categories_collection.find_one = AsyncMock(return_value={"_id": category_id, "label": "Reading", "active": False})
        with self.assertRaises(HTTPException) as raised:
            await clock.clock_in(request, clock.ClockInRequest(category_id=str(category_id)))
        self.assertEqual(raised.exception.status_code, 422)
        with self.assertRaises(HTTPException) as raised:
            await clock.clock_in(request, clock.ClockInRequest(category_id="nope"))
        self.assertEqual(raised.exception.status_code, 422)

        with self.assertRaises(HTTPException) as raised:
            await clock.clock_out(request)
        self.assertEqual(raised.exception.status_code, 409)

    async def test_endpoints_report_nothing_to_change(self):
        state_manager = SimpleNamespace(
            record_pullup=AsyncMock(return_value=7),
            remove_pullup=AsyncMock(return_value=None),
            record_distraction=AsyncMock(return_value=None),
            remove_distraction=AsyncMock(return_value=None),
        )
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(state_manager=state_manager)))
        counters = self.m.counters

        self.assertEqual(await counters.add_pullup(request), {"today": 7})
        state_manager.record_pullup.assert_awaited_once_with(source="api")
        for handler, status in ((counters.remove_last_pullup, 404), (counters.add_distraction, 409),
                                (counters.remove_distraction, 409)):
            with self.subTest(handler=handler.__name__), self.assertRaises(HTTPException) as raised:
                await handler(request)
            self.assertEqual(raised.exception.status_code, status)


class GPIOCounterButtonTests(CounterTestCase):
    def controller(self, distraction_result=None):
        self.state = SimpleNamespace(
            loop=MagicMock(),
            is_clocked_in=MagicMock(return_value=True),
            record_pullup=AsyncMock(return_value=1),
            record_distraction=AsyncMock(return_value=distraction_result),
            announce_press=MagicMock(),
        )
        # The counters' jobs from pins.py; the dashboard can change them.
        self.m.gpio_handler.button_service.assignments = {
            22: {"action": "pullup", "category_id": None, "tags": ""},
            23: {"action": "distraction", "category_id": None, "tags": ""},
        }
        return self.m.gpio_handler.GPIOController(self.state)

    def button_on(self, controller, pin):
        return next(button for button in controller.buttons if button.pin == pin)

    def press(self, button):
        # Run the scheduled coroutine the way the event loop would.
        button.when_pressed()
        callback = self.state.loop.call_soon_threadsafe.call_args.args[0]
        with patch.object(self.m.gpio_handler.asyncio, "create_task", side_effect=lambda coro: coro):
            return callback()

    async def test_activity_buttons_use_the_assignment_at_press_time(self):
        controller = self.controller()
        self.state.toggle_activity = AsyncMock()
        controller.sync_led = MagicMock()
        buttons = self.m.gpio_handler.button_service
        buttons.assignments = {27: {"category_id": "c1", "tags": "deep_work"}}

        await self.press(self.button_on(controller, 27))
        self.state.toggle_activity.assert_awaited_once_with("c1", "deep_work")
        # Every press is announced, so Settings can show which button it was.
        self.state.announce_press.assert_called_once_with(27)

        # Unassigned in the dashboard: the press does nothing.
        buttons.assignments = {27: {"category_id": None, "tags": ""}}
        await self.press(self.button_on(controller, 27))
        self.state.toggle_activity.assert_awaited_once()

    async def test_any_button_can_count_and_the_counters_can_clock_in(self):
        controller = self.controller()
        self.state.toggle_activity = AsyncMock()
        controller.sync_led = MagicMock()
        buttons = self.m.gpio_handler.button_service
        buttons.assignments[27] = {"action": "pullup", "category_id": None, "tags": ""}
        buttons.assignments[22] = {"action": "activity", "category_id": "c1", "tags": ""}

        await self.press(self.button_on(controller, 27))
        self.state.record_pullup.assert_awaited_once_with()
        await self.press(self.button_on(controller, 22))
        self.state.toggle_activity.assert_awaited_once_with("c1", "")

        # "none" does nothing at all.
        buttons.assignments[23] = {"action": "none", "category_id": None, "tags": ""}
        await self.press(self.button_on(controller, 23))
        self.state.record_distraction.assert_not_awaited()

    async def test_counter_buttons_use_pins_22_and_23_with_pull_ups(self):
        controller = self.controller()
        pins = [button.pin for button in controller.buttons]
        self.assertEqual(pins, [2, 3, 4, 27, 22, 23])
        for pin in (22, 23):
            self.assertTrue(self.button_on(controller, pin).kwargs["pull_up"])

    def scheduled(self):
        return [call.args for call in self.state.loop.call_later.call_args_list]

    async def test_each_pullup_press_flashes_and_a_pause_confirms_the_set(self):
        controller = self.controller()
        await self.press(self.button_on(controller, 22))
        self.state.record_pullup.assert_awaited_once_with()
        # Clocked in, so the LED is on: one flash turns it off, back on, then resyncs.
        steps = self.scheduled()
        self.assertEqual([(delay, callback.__name__, rest) for delay, callback, *rest in steps[:2]],
                         [(0, "_show", [False]), (0.1, "_show", [True])])
        self.assertEqual(steps[2][:2], (0.2, controller.sync_led))
        # Then, 3 seconds after the last tap, a double flash for the saved set.
        self.assertEqual(steps[3][0], 3.0)
        self.state.loop.call_later.reset_mock()
        steps[3][1]()
        self.assertEqual([args[0] for args in self.scheduled()], [0, 0.1, 0.2, 0.30000000000000004, 0.4])

    async def test_a_new_flash_replaces_one_still_running(self):
        controller = self.controller()
        controller.flash_led()
        first = self.state.loop.call_later.return_value
        controller.flash_led()
        self.assertGreaterEqual(first.cancel.call_count, 3)

    async def test_distraction_press_flashes_only_when_counted(self):
        controller = self.controller(distraction_result=None)
        await self.press(self.button_on(controller, 23))
        self.state.record_distraction.assert_awaited_once_with()
        self.state.loop.call_later.assert_not_called()

        controller = self.controller(distraction_result={"session_id": "s1", "distractions": 1})
        await self.press(self.button_on(controller, 23))
        # A double flash: four LED steps, then a resync.
        self.assertEqual(self.state.loop.call_later.call_count, 5)


class OverviewCounterTests(CounterTestCase):
    async def test_overview_reports_pullups_and_distractions_by_local_day(self):
        def session(start, end, distractions):
            return {"_id": ObjectId(), "category_id": ObjectId(), "tags": "",
                    "start_time": start, "end_time": end, "distractions": distractions}

        thursday = session(datetime(2026, 9, 10, 18, tzinfo=timezone.utc),
                           datetime(2026, 9, 10, 19, tzinfo=timezone.utc), 2)
        # Started 11:30 PM Thursday in Los Angeles, so it counts on Thursday.
        late_thursday = session(datetime(2026, 9, 11, 6, 30, tzinfo=timezone.utc),
                                datetime(2026, 9, 11, 7, 30, tzinfo=timezone.utc), 1)
        active = session(datetime(2026, 9, 11, 20, tzinfo=timezone.utc), None, 4)
        old_record = {"_id": ObjectId(), "category_id": ObjectId(), "tags": "",
                      "start_time": datetime(2026, 9, 11, 17, tzinfo=timezone.utc),
                      "end_time": datetime(2026, 9, 11, 18, tzinfo=timezone.utc)}

        week = MagicMock(); week.to_list = AsyncMock(return_value=[thursday, late_thursday, old_record, active])
        day = MagicMock(); day.sort.return_value = day
        day.to_list = AsyncMock(return_value=[old_record, active])
        self.db.sessions_collection.find.side_effect = [week, day]
        self.db.sessions_collection.find_one = AsyncMock(return_value=active)
        self.db.categories_collection.find.return_value.to_list = AsyncMock(return_value=[])
        pullup_times = [
            datetime(2026, 9, 11, 6, 59, tzinfo=timezone.utc),  # 11:59 PM Thursday
            datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc),   # midnight Friday
            datetime(2026, 9, 11, 16, tzinfo=timezone.utc),
            datetime(2026, 9, 11, 16, 1, tzinfo=timezone.utc),
        ]
        self.db.pullups_collection.find.return_value.to_list = AsyncMock(
            return_value=[{"created_at": time} for time in pullup_times])

        result = await self.m.overview_service.OverviewService().get_overview(str(USER_ID))

        self.assertEqual(result["day"]["pullups"], 3)
        self.assertEqual(result["day"]["distractions"], 4)
        self.assertEqual(result["day"]["active_session"]["distractions"], 4)
        graph = result["week"]["graph"]
        self.assertEqual([day["pullups"] for day in graph], [0, 0, 0, 1, 3, 0, 0])
        self.assertEqual([day["distractions"] for day in graph], [0, 0, 0, 3, 4, 0, 0])
        self.assertEqual((result["week"]["pullups"], result["week"]["distractions"]), (4, 7))
        query = self.db.pullups_collection.find.call_args.args[0]
        self.assertEqual(query["user_id"], USER_ID)
        # Monday 00:00 to the next Monday 00:00 in Los Angeles.
        self.assertEqual(query["created_at"], {
            "$gte": datetime(2026, 9, 7, 7, tzinfo=timezone.utc),
            "$lt": datetime(2026, 9, 14, 7, tzinfo=timezone.utc),
        })


if __name__ == "__main__":
    unittest.main()
