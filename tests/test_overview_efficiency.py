import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId


class OverviewEfficiencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_sessions_split_once_without_changing_cross_midnight_totals(self):
        collection = MagicMock()
        database = ModuleType("app.core.database")
        database.sessions_collection = collection
        spec = importlib.util.spec_from_file_location(
            "overview_under_test",
            Path(__file__).resolve().parents[1] / "app/services/overview_service.py",
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"app.core.database": database}):
            spec.loader.exec_module(module)
        now = datetime(2026, 9, 11, 21, tzinfo=timezone.utc)
        prior = {"_id": ObjectId(), "start_time": datetime(2026, 9, 10, 23, tzinfo=timezone.utc),
                 "end_time": datetime(2026, 9, 11, 9, tzinfo=timezone.utc)}
        active = {"_id": ObjectId(), "start_time": datetime(2026, 9, 11, 20, tzinfo=timezone.utc),
                  "end_time": None}
        week = MagicMock(); week.to_list = AsyncMock(return_value=[prior, active])
        day = MagicMock(); day.sort.return_value = day
        day.to_list = AsyncMock(return_value=[active])
        collection.find.side_effect = [week, day]
        collection.find_one = AsyncMock(return_value=active)
        service = module.OverviewService()
        with patch.object(module, "datetime") as clock, patch.object(
            service, "_split_session_by_local_day", wraps=service._split_session_by_local_day
        ) as split:
            clock.now.return_value = now
            result = await service.get_overview(str(ObjectId()))
        self.assertEqual(split.call_count, 2)
        self.assertEqual(result["day"]["worked_seconds"], 3 * 3600)
        self.assertEqual(result["day"]["longest_session_seconds"], 2 * 3600)
        self.assertEqual(result["week"]["total_time_seconds"], 11 * 3600)
        self.assertEqual(result["week"]["session_count"], 2)
        self.assertEqual(result["week"]["goal_completed_days"], 1)
        self.assertEqual([day["seconds"] for day in result["week"]["graph"]],
                         [0, 0, 0, 8 * 3600, 3 * 3600, 0, 0])
