import importlib
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId

USER_ID = ObjectId()
# 21:00 UTC is 14:00 on Friday, September 11, in Los Angeles (UTC-7).
NOW = datetime(2026, 9, 11, 21, tzinfo=timezone.utc)
CREATING = {"_id": ObjectId("69c2eb61c3192568a8a3b370"), "label": "Creating", "color": "#c98500"}
PIANISO = {"_id": ObjectId("6a02b0c85f921debb9421cee"), "label": "Pianiso", "color": None,
           "tag_colors": {"technical": "#e66767"}}


def la(day, hour, minute=0, second=0):
    # A Los Angeles wall-clock time in September, as UTC.
    return datetime(2026, 9, day, hour, minute, second, tzinfo=timezone.utc) + timedelta(hours=7)


def load():
    database = ModuleType("app.core.database")
    for name in ("sessions_collection", "events_collection", "categories_collection", "pullups_collection",
                 "notes_collection"):
        setattr(database, name, MagicMock())
    config = ModuleType("app.core.config")
    config.settings = SimpleNamespace(SESSION_CATEGORY="CREATING")
    names = ("app.services.overview_service", "app.services.pullup_service", "app.services.calendar_service")
    with patch.dict(sys.modules, {"app.core.database": database, "app.core.config": config}):
        for name in names:
            sys.modules.pop(name, None)
        module = importlib.import_module("app.services.calendar_service")
    return database, module


def found(rows):
    query = MagicMock()
    query.sort.return_value.to_list = AsyncMock(return_value=rows)
    return query


class CalendarTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_day_lays_out_sessions_markers_and_its_breakdown(self):
        db, module = load()
        # Thursday 11:30 PM to Friday 1:00 AM, so it shows on both days.
        late = {"_id": ObjectId(), "category_id": CREATING["_id"], "tags": "",
                "start_time": la(10, 23, 30), "end_time": la(11, 1), "distractions": 0}
        # Running since Friday 1:00 PM.
        running = {"_id": ObjectId(), "category_id": PIANISO["_id"], "tags": "technical",
                   "start_time": la(11, 13), "end_time": None, "distractions": 2}
        sid = str(running["_id"])
        events = [
            {"session_id": sid, "event_type": "distraction", "created_at": la(11, 13, 10)},
            {"session_id": sid, "event_type": "distraction", "created_at": la(11, 13, 20)},
            {"session_id": sid, "event_type": "distraction_removed", "created_at": la(11, 13, 21)},
            {"session_id": sid, "event_type": "distraction", "created_at": la(11, 13, 40)},
        ]
        # Four quick taps, a 10-second rest, then two more: sets of 4 and 2.
        taps = [la(11, 13, 30, second) for second in (0, 1, 2, 3, 13, 14)]
        note = {"_id": ObjectId(), "session_id": running["_id"], "text": "Scales", "at": la(11, 13, 45)}
        db.sessions_collection.find.return_value = found([late, running])
        db.categories_collection.find.return_value.to_list = AsyncMock(return_value=[CREATING, PIANISO])
        db.events_collection.find.return_value = found(events)
        db.pullups_collection.find.return_value = found([{"created_at": tap} for tap in taps])
        db.notes_collection.find.return_value = found([note])

        with patch.object(module, "datetime") as clock:
            clock.now.return_value = NOW
            clock.combine = datetime.combine
            calendar = await module.CalendarService().get_calendar(str(USER_ID), date(2026, 9, 10), 2)

        thursday, friday = calendar["entries"]
        # Thursday's part runs to midnight.
        self.assertEqual([(block["start_minute"], block["end_minute"]) for block in thursday["blocks"]], [(23 * 60 + 30, 1440)])
        self.assertEqual(thursday["worked_seconds"], 30 * 60)
        early, live = friday["blocks"]
        self.assertEqual((early["start_minute"], early["end_minute"], early["end"]), (0, 60, la(11, 1)))
        self.assertEqual(early["session_seconds"], 90 * 60)
        self.assertEqual((live["start_minute"], live["end_minute"], live["end"], live["is_active"]), (780, 840, None, True))
        self.assertEqual(live["category"]["tag_colors"], {"technical": "#e66767"})
        self.assertEqual(friday["worked_seconds"], 2 * 3600)
        self.assertEqual([(item["label"], item["tags"], item["seconds"], item["is_active"]) for item in friday["categories"]],
                         [("Creating", "", 3600, False), ("Pianiso", "technical", 3600, True)])

        markers = [(marker["kind"], marker["minute"], marker.get("count"), marker.get("text")) for marker in friday["markers"]]
        self.assertEqual(markers, [
            ("distraction", 790, None, None),
            ("pullups", 810, 4, None),
            ("pullups", 810 + 13 / 60, 2, None),
            ("distraction", 820, None, None),
            ("note", 825, None, "Scales"),
        ])
        self.assertEqual(thursday["markers"], [])
        # Midnight Thursday to midnight Saturday in Los Angeles.
        query = db.sessions_collection.find.call_args.args[0]
        self.assertEqual(query["start_time"], {"$lt": la(12, 0)})
        self.assertEqual(query["$or"][0], {"end_time": {"$gte": la(10, 0)}})

    def test_distraction_replay_keeps_the_latest_presses_after_a_lower_edit(self):
        _, module = load()
        presses = [{"event_type": "distraction", "created_at": la(11, 9, minute)} for minute in (1, 2, 3)]
        self.assertEqual(module.distraction_times(presses, 3), [la(11, 9, 1), la(11, 9, 2), la(11, 9, 3)])
        self.assertEqual(module.distraction_times(presses, 1), [la(11, 9, 3)])
        removed = presses + [{"event_type": "distraction_removed", "created_at": la(11, 9, 4)}]
        self.assertEqual(module.distraction_times(removed, 5), [la(11, 9, 1), la(11, 9, 2)])


if __name__ == "__main__":
    unittest.main()
