import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId

PIANISO = {"_id": ObjectId("6a02b0c85f921debb9421cee"), "label": "Pianiso", "color": None}


def session(start_hour, end_hour, tags, day=11):
    return {
        "_id": ObjectId(), "category_id": PIANISO["_id"], "tags": tags,
        "start_time": datetime(2026, 9, day, start_hour, tzinfo=timezone.utc),
        "end_time": datetime(2026, 9, day, end_hour, tzinfo=timezone.utc) if end_hour else None,
    }


class OverviewStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_reports_active_category_and_each_days_makeup(self):
        sessions, categories = MagicMock(), MagicMock()
        database = ModuleType("app.core.database")
        database.sessions_collection = sessions
        database.categories_collection = categories
        database.pullups_collection = MagicMock()
        database.pullups_collection.find.return_value.to_list = AsyncMock(return_value=[])
        spec = importlib.util.spec_from_file_location(
            "overview_status_under_test",
            Path(__file__).resolve().parents[1] / "app/services/overview_service.py",
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"app.core.database": database}):
            spec.loader.exec_module(module)

        # 21:00 UTC is 14:00 on Friday in Los Angeles.
        now = datetime(2026, 9, 11, 21, tzinfo=timezone.utc)
        earlier_same = session(16, 17, "technical")
        other_tag = session(17, 18, "non_technical")
        yesterday_same = session(16, 17, "technical", day=10)
        active = session(20, None, "technical")
        active["start_time"] = active["start_time"].replace(minute=30)

        week = MagicMock()
        week.to_list = AsyncMock(return_value=[yesterday_same, earlier_same, other_tag, active])
        day = MagicMock()
        day.sort.return_value = day
        day.to_list = AsyncMock(return_value=[earlier_same, other_tag, active])
        sessions.find.side_effect = [week, day]
        sessions.find_one = AsyncMock(return_value=active)
        categories.find.return_value.to_list = AsyncMock(return_value=[PIANISO])

        with patch.object(module, "datetime") as clock:
            clock.now.return_value = now
            result = await module.OverviewService().get_overview(str(ObjectId()))

        active_session = result["day"]["active_session"]
        self.assertEqual(active_session["category"], {
            "id": str(PIANISO["_id"]), "label": "Pianiso", "color": None, "tag_colors": {},
        })
        self.assertEqual(active_session["tags"], "technical")
        categories.find.assert_called_once_with({"_id": {"$in": [PIANISO["_id"]]}})

        # Friday's makeup, biggest first; the running session is marked active.
        friday = result["week"]["graph"][4]["categories"]
        self.assertEqual(
            [(item["label"], item["tags"], item["seconds"], item["is_active"]) for item in friday],
            [("Pianiso", "technical", 3600 + 1800, True), ("Pianiso", "non_technical", 3600, False)],
        )
        thursday = result["week"]["graph"][3]["categories"]
        self.assertEqual([(item["tags"], item["seconds"]) for item in thursday], [("technical", 3600)])
        self.assertEqual(result["week"]["graph"][5]["categories"], [])


if __name__ == "__main__":
    unittest.main()
