import importlib
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId
from fastapi import HTTPException

USER_ID = ObjectId()
# 21:00 UTC is 14:00 on Friday, September 11, in Los Angeles.
NOW = datetime(2026, 9, 11, 21, tzinfo=timezone.utc)
# Creating is on the GPIO 4 button and Pianiso on GPIO 2 and 3 (app/hardware/pins.py).
CREATING = {"_id": ObjectId("69c2eb61c3192568a8a3b370"), "key": "creating", "label": "Creating", "color": None}
PIANISO = {"_id": ObjectId("6a02b0c85f921debb9421cee"), "key": "pianiso", "label": "Pianiso", "color": None,
           "tags": ["warmup"]}
READING = {"_id": ObjectId(), "key": "reading", "label": "Reading", "color": "#3b82f6", "tags": []}

MODULES = ("app.services.note_service", "app.services.session_service", "app.services.overview_service",
           "app.services.button_service", "app.api.v1.endpoints.buttons",
           "app.services.category_service", "app.services.worklog_service",
           "app.api.v1.endpoints.categories", "app.api.v1.endpoints.notes")


def load_modules():
    # Import against fake collections so these tests never reach MongoDB or GPIO.
    database = ModuleType("app.core.database")
    for name in ("sessions_collection", "events_collection", "categories_collection", "pullups_collection",
                 "notes_collection", "buttons_collection"):
        setattr(database, name, MagicMock())
    config = ModuleType("app.core.config")
    config.settings = SimpleNamespace(SESSION_CATEGORY="CREATING")
    with patch.dict(sys.modules, {"app.core.database": database, "app.core.config": config}):
        for name in MODULES:
            sys.modules.pop(name, None)
        modules = SimpleNamespace(**{name.rsplit(".", 1)[1]: importlib.import_module(name) for name in MODULES})
    return database, modules


def cursor_of(rows):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=rows)
    return cursor


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db, self.m = load_modules()
        for module in (self.m.note_service, self.m.session_service, self.m.category_service, self.m.worklog_service):
            clock = patch.object(module, "datetime")
            fake = clock.start()
            fake.now.return_value = NOW
            fake.combine = datetime.combine
            fake.min = datetime.min
            self.addCleanup(clock.stop)


class CategoryTests(Base):
    def setUp(self):
        super().setUp()
        self.service = self.m.category_service.category_service
        # The assignments from pins.py: Creating on GPIO 4, Pianiso on 2 and 3.
        self.m.button_service.button_service.use_defaults()
        self.db.sessions_collection.aggregate = AsyncMock(return_value=cursor_of([]))

    async def test_create_cleans_input_and_rejects_duplicate_names(self):
        self.db.categories_collection.find_one = AsyncMock(return_value=None)
        self.db.categories_collection.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId()))

        created = await self.service.create_category(str(USER_ID), {
            "label": " Deep Reading ", "color": "#3B82F6",
            "tags": ["Deep Work", "deep-work", "  "],
            "tag_colors": {"Deep work": "#EF4444", "unused": "#000000"},
        })

        saved = self.db.categories_collection.insert_one.await_args.args[0]
        self.assertEqual((saved["label"], saved["key"], saved["color"]), ("Deep Reading", "deep_reading", "#3b82f6"))
        self.assertEqual(saved["tags"], ["deep_work"])
        # Colors only for the category's own tags.
        self.assertEqual(saved["tag_colors"], {"deep_work": "#ef4444"})
        self.assertTrue(saved["active"])
        self.assertEqual((created["session_count"], created["buttons"]), (0, []))

        self.db.categories_collection.find_one = AsyncMock(return_value=READING)
        with self.assertRaises(self.m.category_service.CategoryError) as raised:
            await self.service.create_category(str(USER_ID), {"label": "reading"})
        # Names the existing category as it's spelled.
        self.assertEqual((str(raised.exception), raised.exception.status_code),
                         ("A category named Reading already exists.", 409))

    async def test_update_renames_recolors_and_protects_button_categories(self):
        # Finds Creating by its id; the name-uniqueness check finds nothing.
        self.db.categories_collection.find_one = AsyncMock(side_effect=lambda query, **_: (
            dict(CREATING) if query.get("_id") == CREATING["_id"] else None))
        self.db.categories_collection.update_one = AsyncMock()

        result = await self.service.update_category(str(USER_ID), str(CREATING["_id"]), {
            "label": "Making", "color": "#22C55E", "tags": ["Sketching"],
        })
        _, update = self.db.categories_collection.update_one.await_args.args
        self.assertEqual({key: update["$set"][key] for key in ("label", "color", "tags")},
                         {"label": "Making", "color": "#22c55e", "tags": ["sketching"]})
        self.assertEqual([button["pin"] for button in result["buttons"]], [4])

        with self.assertRaises(self.m.category_service.CategoryError) as raised:
            await self.service.update_category(str(USER_ID), str(CREATING["_id"]), {"active": False})
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("GPIO 4", str(raised.exception))

        with self.assertRaises(self.m.category_service.CategoryError) as raised:
            await self.service.update_category(str(USER_ID), str(ObjectId()), {"label": "x"})
        self.assertEqual(raised.exception.status_code, 404)

    async def test_delete_only_unused_categories_without_buttons(self):
        error = self.m.category_service.CategoryError
        self.db.categories_collection.delete_one = AsyncMock()

        self.db.categories_collection.find_one = AsyncMock(return_value=CREATING)
        with self.assertRaises(error) as raised:
            await self.service.delete_category(str(USER_ID), str(CREATING["_id"]))
        self.assertIn("GPIO 4", str(raised.exception))

        self.db.categories_collection.find_one = AsyncMock(return_value=READING)
        self.db.sessions_collection.count_documents = AsyncMock(return_value=3)
        with self.assertRaises(error) as raised:
            await self.service.delete_category(str(USER_ID), str(READING["_id"]))
        self.assertEqual(str(raised.exception), "3 sessions use Reading. Archive it instead to hide it and keep its history.")
        self.db.categories_collection.delete_one.assert_not_awaited()

        self.db.sessions_collection.count_documents = AsyncMock(return_value=0)
        await self.service.delete_category(str(USER_ID), str(READING["_id"]))
        self.db.categories_collection.delete_one.assert_awaited_once_with({"_id": READING["_id"]})

    async def test_list_reports_usage_buttons_and_picker_tags(self):
        self.db.categories_collection.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[PIANISO, READING])
        last = NOW - timedelta(hours=3)
        self.db.sessions_collection.aggregate = AsyncMock(return_value=cursor_of([
            {"_id": PIANISO["_id"], "count": 5, "seconds": 3600.7, "last": last, "tags": ["technical", "non_technical", ""]},
        ]))

        pianiso, reading = await self.service.list_categories(str(USER_ID))

        self.db.categories_collection.find.assert_called_with({"active": {"$ne": False}})
        self.assertEqual(pianiso["tags"], ["", "non_technical", "technical", "warmup"])
        self.assertEqual(pianiso["defined_tags"], ["warmup"])
        self.assertEqual(pianiso["used_tags"], ["non_technical", "technical"])
        self.assertEqual((pianiso["session_count"], pianiso["total_seconds"], pianiso["last_used_at"]), (5, 3600, last))
        self.assertEqual([(button["pin"], button["tags"]) for button in pianiso["buttons"]],
                         [(2, "technical"), (3, "non_technical")])
        self.assertEqual((reading["session_count"], reading["tags"], reading["buttons"]), (0, [""], []))

        await self.service.list_categories(str(USER_ID), include_archived=True)
        self.db.categories_collection.find.assert_called_with({})


class NoteTests(Base):
    def setUp(self):
        super().setUp()
        self.service = self.m.note_service.note_service
        self.db.notes_collection.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId()))

    def saved(self):
        return self.db.notes_collection.insert_one.await_args.args[0]

    async def test_note_joins_the_session_running_at_its_time(self):
        session = {"_id": ObjectId(), "start_time": NOW - timedelta(hours=1), "end_time": None}
        self.db.sessions_collection.find_one = AsyncMock(return_value=session)

        note = await self.service.create_note(str(USER_ID), {"text": "  Wrote the intro ", "at": NOW - timedelta(minutes=10)})

        self.assertEqual((self.saved()["session_id"], self.saved()["text"]), (session["_id"], "Wrote the intro"))
        self.assertEqual(note["at"], NOW - timedelta(minutes=10))
        query = self.db.sessions_collection.find_one.await_args.args[0]
        self.assertEqual(query["start_time"], {"$lte": NOW - timedelta(minutes=10)})

    async def test_note_outside_sessions_stands_alone_and_input_is_checked(self):
        self.db.sessions_collection.find_one = AsyncMock(return_value=None)
        await self.service.create_note(str(USER_ID), {"text": "Planned tomorrow"})
        self.assertEqual((self.saved()["session_id"], self.saved()["at"]), (None, NOW))

        # A browser clock a little ahead is clamped to now.
        await self.service.create_note(str(USER_ID), {"text": "Done", "at": NOW + timedelta(seconds=30)})
        self.assertEqual(self.saved()["at"], NOW)

        for data, message in (({"text": "x", "at": NOW + timedelta(minutes=5)}, "Notes can't be in the future."),
                              ({"text": "   "}, "Write something first.")):
            with self.subTest(data=data), self.assertRaises(self.m.note_service.NoteError) as raised:
                await self.service.create_note(str(USER_ID), data)
            self.assertEqual(str(raised.exception), message)

    async def test_a_chosen_session_needs_a_time_during_it(self):
        session = {"_id": ObjectId(), "user_id": USER_ID,
                   "start_time": NOW - timedelta(hours=2), "end_time": NOW - timedelta(hours=1)}
        self.db.sessions_collection.find_one = AsyncMock(return_value=session)
        error = self.m.note_service.NoteError

        with self.assertRaises(error) as raised:
            await self.service.create_note(str(USER_ID), {
                "text": "x", "at": NOW - timedelta(minutes=30), "session_id": str(session["_id"])})
        self.assertEqual(str(raised.exception), "Pick a time during this session.")

        await self.service.create_note(str(USER_ID), {
            "text": "Fixed the bug", "at": NOW - timedelta(minutes=90), "session_id": str(session["_id"])})
        self.assertEqual(self.saved()["session_id"], session["_id"])

        self.db.sessions_collection.find_one = AsyncMock(return_value=None)
        with self.assertRaises(error) as raised:
            await self.service.create_note(str(USER_ID), {"text": "x", "session_id": str(ObjectId())})
        self.assertEqual(raised.exception.status_code, 404)

    async def test_moving_a_note_in_time_moves_it_to_that_session(self):
        note = {"_id": ObjectId(), "user_id": USER_ID, "session_id": ObjectId(), "text": "Old",
                "at": NOW - timedelta(hours=3), "created_at": NOW, "updated_at": NOW}
        own_session = {"_id": note["session_id"], "start_time": NOW - timedelta(hours=4),
                       "end_time": NOW - timedelta(hours=2)}
        other_session = {"_id": ObjectId(), "start_time": NOW - timedelta(hours=1), "end_time": None}
        self.db.notes_collection.find_one = AsyncMock(return_value=dict(note))
        self.db.notes_collection.update_one = AsyncMock()
        self.db.sessions_collection.find_one = AsyncMock(side_effect=lambda query, **_: (
            own_session if query.get("_id") == note["session_id"] else other_session))

        moved = await self.service.update_note(str(USER_ID), str(note["_id"]), {"at": NOW - timedelta(minutes=5)})
        _, update = self.db.notes_collection.update_one.await_args.args
        self.assertEqual(update["$set"]["session_id"], other_session["_id"])
        self.assertEqual(moved["session_id"], str(other_session["_id"]))

        await self.service.update_note(str(USER_ID), str(note["_id"]), {"text": "New"})
        _, update = self.db.notes_collection.update_one.await_args.args
        self.assertNotIn("session_id", update["$set"])

    async def test_a_note_saved_just_before_its_session_starts_stays_in_it(self):
        # The time field drops seconds: a note at 9:30:40 in a session from
        # 9:30:20 comes back as 9:30:00.
        session = {"_id": ObjectId(), "start_time": NOW - timedelta(minutes=10, seconds=-20), "end_time": None}
        note = {"_id": ObjectId(), "user_id": USER_ID, "session_id": session["_id"], "text": "Old",
                "at": NOW - timedelta(minutes=10, seconds=-40), "created_at": NOW, "updated_at": NOW}
        self.db.notes_collection.find_one = AsyncMock(return_value=dict(note))
        self.db.notes_collection.update_one = AsyncMock()
        self.db.sessions_collection.find_one = AsyncMock(side_effect=lambda query, **_: (
            session if query.get("_id") == session["_id"] else None))

        kept = await self.service.update_note(str(USER_ID), str(note["_id"]), {"at": NOW - timedelta(minutes=10)})
        self.assertEqual(kept["session_id"], str(session["_id"]))


class SessionNoteTests(Base):
    async def test_deleting_a_session_keeps_its_notes(self):
        session = {"_id": ObjectId(), "user_id": USER_ID, "status": "completed",
                   "start_time": NOW - timedelta(hours=2), "end_time": NOW - timedelta(hours=1)}
        self.db.sessions_collection.find_one = AsyncMock(return_value=session)
        self.db.sessions_collection.delete_one = AsyncMock()
        self.db.events_collection.delete_many = AsyncMock()
        self.db.notes_collection.update_many = AsyncMock()

        await self.m.session_service.session_service.delete_session(str(USER_ID), str(session["_id"]))

        self.db.notes_collection.update_many.assert_awaited_once_with(
            {"session_id": session["_id"]}, {"$set": {"session_id": None}})

    async def test_sessions_table_rows_carry_their_notes(self):
        session = {"_id": ObjectId(), "user_id": USER_ID, "category_id": CREATING["_id"], "status": "completed",
                   "start_time": NOW - timedelta(hours=2), "end_time": NOW - timedelta(hours=1), "elapsed_time": 3600}
        self.db.sessions_collection.count_documents = AsyncMock(return_value=1)
        (self.db.sessions_collection.find.return_value.sort.return_value.skip.return_value
         .limit.return_value.to_list) = AsyncMock(return_value=[session])
        self.db.categories_collection.find.return_value.to_list = AsyncMock(return_value=[CREATING])
        self.db.notes_collection.aggregate = AsyncMock(return_value=cursor_of([
            {"_id": session["_id"], "count": 2, "latest": "Fixed the login bug"},
        ]))

        page = await self.m.session_service.session_service.list_sessions(str(USER_ID))

        item = page["items"][0]
        self.assertEqual((item["note_count"], item["latest_note"]), (2, "Fixed the login bug"))
        self.assertEqual(item["category"]["tag_colors"], {})


class WorklogTests(Base):
    async def test_worklog_lists_each_days_sessions_with_their_notes(self):
        thursday = {"_id": ObjectId(), "category_id": CREATING["_id"], "tags": "",
                    "start_time": datetime(2026, 9, 10, 16, tzinfo=timezone.utc),
                    "end_time": datetime(2026, 9, 10, 17, tzinfo=timezone.utc)}
        running = {"_id": ObjectId(), "category_id": PIANISO["_id"], "tags": "technical", "distractions": 2,
                   "start_time": datetime(2026, 9, 11, 20, tzinfo=timezone.utc), "end_time": None}

        def note(at, session_id, text):
            return {"_id": ObjectId(), "session_id": session_id, "text": text, "at": at, "created_at": at, "updated_at": at}

        during = note(datetime(2026, 9, 11, 20, 30, tzinfo=timezone.utc), running["_id"], "Scales")
        alone = note(datetime(2026, 9, 10, 18, tzinfo=timezone.utc), None, "Called the bank")
        # Its session started before the range, so it stands alone on its own day.
        orphan = note(datetime(2026, 9, 11, 18, tzinfo=timezone.utc), ObjectId(), "Reviewed notes")
        self.db.sessions_collection.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[thursday, running])
        self.db.notes_collection.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[alone, orphan, during])
        self.db.categories_collection.find.return_value.to_list = AsyncMock(return_value=[CREATING, PIANISO])
        # Two pull-ups Friday evening in Los Angeles, though it's Saturday in UTC.
        self.db.pullups_collection.find.return_value.to_list = AsyncMock(return_value=[
            {"created_at": datetime(2026, 9, 12, 2, tzinfo=timezone.utc)},
            {"created_at": datetime(2026, 9, 12, 2, 1, tzinfo=timezone.utc)},
        ])

        log = await self.m.worklog_service.worklog_service.get_worklog(str(USER_ID), 2)

        friday, thursday_entry = log["entries"]
        self.assertEqual((friday["date"], friday["worked_seconds"], friday["session_count"]), ("2026-09-11", 3600, 1))
        self.assertEqual((friday["pullups"], thursday_entry["pullups"]), (2, 0))
        session = friday["sessions"][0]
        self.assertEqual((session["is_active"], session["seconds"], session["tags"], session["distractions"]),
                         (True, 3600, "technical", 2))
        self.assertEqual(session["category"]["label"], "Pianiso")
        self.assertEqual([item["text"] for item in session["notes"]], ["Scales"])
        self.assertEqual([item["text"] for item in friday["notes"]], ["Reviewed notes"])
        self.assertEqual((thursday_entry["date"], thursday_entry["worked_seconds"]), ("2026-09-10", 3600))
        self.assertEqual([item["text"] for item in thursday_entry["notes"]], ["Called the bank"])
        # From midnight Thursday to midnight Saturday in Los Angeles.
        query = self.db.notes_collection.find.call_args.args[0]
        self.assertEqual(query["at"], {"$gte": datetime(2026, 9, 10, 7, tzinfo=timezone.utc),
                                       "$lt": datetime(2026, 9, 12, 7, tzinfo=timezone.utc)})


class ButtonTests(Base):
    def setUp(self):
        super().setUp()
        self.service = self.m.button_service.button_service
        self.db.buttons_collection.insert_one = AsyncMock()
        self.db.buttons_collection.update_one = AsyncMock()

    async def test_first_start_saves_pins_py_and_stored_assignments_win(self):
        stored_toycon = {"pin": 27, "category_id": None, "tags": ""}
        self.db.buttons_collection.find.return_value.to_list = AsyncMock(return_value=[stored_toycon])

        await self.service.load()

        # GPIO 27 was unassigned in the dashboard; the others start from pins.py.
        self.assertIsNone(self.service.get(27))
        self.assertEqual(self.service.get(4), {"category_id": str(CREATING["_id"]), "tags": ""})
        self.assertEqual(self.service.get(2)["tags"], "technical")
        saved = [call.args[0] for call in self.db.buttons_collection.insert_one.await_args_list]
        self.assertEqual([(doc["pin"], doc["action"]) for doc in saved],
                         [(2, "activity"), (3, "activity"), (4, "activity"), (22, "pullup"), (23, "distraction")])
        # A button saved before actions existed keeps working from its category.
        self.assertEqual((self.service.get_action(27), self.service.get_action(22)), ("none", "pullup"))
        self.db.categories_collection.find.return_value.to_list = AsyncMock(return_value=[CREATING])
        self.assertEqual([button["pin"] for button in await self.service.list_buttons()], [2, 3, 4, 27, 22, 23])

    async def test_assigning_validates_and_takes_effect_at_once(self):
        self.service.use_defaults()
        self.db.categories_collection.find_one = AsyncMock(return_value=READING)

        result = await self.service.assign(27, str(READING["_id"]), "Deep Work")
        self.assertEqual((result["category"]["label"], result["tags"]), ("Reading", "deep_work"))
        self.assertEqual(self.service.get(27), {"category_id": str(READING["_id"]), "tags": "deep_work"})
        self.assertEqual([button["pin"] for button in self.service.button_map()[str(READING["_id"])]], [27])
        query, update = self.db.buttons_collection.update_one.await_args.args
        self.assertEqual((query, update["$set"]["category_id"]), ({"pin": 27}, READING["_id"]))

        unassigned = await self.service.assign(27, None, "ignored")
        self.assertEqual((unassigned["category"], unassigned["tags"]), (None, ""))
        self.assertIsNone(self.service.get(27))

        error = self.m.button_service.ButtonError
        with self.assertRaises(error) as raised:
            await self.service.assign(17, None, "")
        self.assertEqual(raised.exception.status_code, 404)

        # Any button can count, and a counter button can clock in.
        counted = await self.service.assign(27, None, "", "distraction")
        self.assertEqual((counted["action"], counted["category"]), ("distraction", None))
        self.assertEqual((self.service.get_action(27), self.service.get(27)), ("distraction", None))
        self.assertNotIn(str(READING["_id"]), self.service.button_map())
        clocking = await self.service.assign(22, str(READING["_id"]), "", "activity")
        self.assertEqual(clocking["action"], "activity")
        with self.assertRaises(error):
            await self.service.assign(23, None, "", "activity")
        self.db.categories_collection.find_one = AsyncMock(return_value={**READING, "active": False})
        with self.assertRaises(error) as raised:
            await self.service.assign(27, str(READING["_id"]), "")
        self.assertEqual(str(raised.exception), "Reading is archived. Restore it first.")

    async def test_an_unassigned_button_lets_its_category_be_archived(self):
        self.service.use_defaults()
        self.db.categories_collection.find_one = AsyncMock(side_effect=lambda query, **_: (
            dict(CREATING) if query.get("_id") == CREATING["_id"] else None))
        self.db.categories_collection.update_one = AsyncMock()
        self.db.sessions_collection.aggregate = AsyncMock(return_value=cursor_of([]))
        await self.service.assign(4, None, "")

        result = await self.m.category_service.category_service.update_category(
            str(USER_ID), str(CREATING["_id"]), {"active": False})
        self.assertFalse(result["active"])


class EndpointTests(Base):
    def request(self):
        self.notify = MagicMock()
        state = SimpleNamespace(user_id=USER_ID, state_manager=SimpleNamespace(notify_dashboards=self.notify))
        return SimpleNamespace(app=SimpleNamespace(state=state))

    async def test_changes_refresh_dashboards_and_errors_keep_their_status(self):
        categories, notes = self.m.categories, self.m.notes
        request = self.request()
        body = categories.CategoryCreateRequest(label="Reading")

        with patch.object(categories.category_service, "create_category", AsyncMock(return_value={"id": "c1"})):
            self.assertEqual(await categories.create_category(request, body), {"id": "c1"})
        self.notify.assert_called_once()

        error = self.m.category_service.CategoryError("Taken", status_code=409)
        with patch.object(categories.category_service, "create_category", AsyncMock(side_effect=error)), \
                self.assertRaises(HTTPException) as raised:
            await categories.create_category(request, body)
        self.assertEqual(raised.exception.status_code, 409)
        self.notify.assert_called_once()

        note_error = self.m.note_service.NoteError("Pick a time during this session.")
        with patch.object(notes.note_service, "create_note", AsyncMock(side_effect=note_error)), \
                self.assertRaises(HTTPException) as raised:
            await notes.create_note(request, notes.NoteCreateRequest(text="x"))
        self.assertEqual(raised.exception.status_code, 422)
        self.notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
