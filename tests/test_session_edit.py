import importlib
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.session_update_request import SessionUpdateRequest

USER_ID = ObjectId()
NOW = datetime(2026, 10, 1, 23, 0, tzinfo=timezone.utc)
CREATING = {"_id": ObjectId("69c2eb61c3192568a8a3b370"), "label": "Creating", "color": None}
PIANISO = {"_id": ObjectId("6a02b0c85f921debb9421cee"), "label": "Pianiso", "color": None}


def load_modules():
    # Import against fake collections so these tests never reach MongoDB or GPIO.
    database = ModuleType("app.core.database")
    for name in ("sessions_collection", "events_collection", "categories_collection", "pullups_collection",
                 "notes_collection"):
        setattr(database, name, MagicMock())
    config = ModuleType("app.core.config")
    config.settings = SimpleNamespace(SESSION_CATEGORY="CREATING")
    with patch.dict(sys.modules, {"app.core.database": database, "app.core.config": config}):
        for name in ("app.services.session_service", "app.services.state_manager",
                     "app.api.v1.endpoints.sessions"):
            sys.modules.pop(name, None)
        sessions = importlib.import_module("app.services.session_service")
        state = importlib.import_module("app.services.state_manager")
        endpoint = importlib.import_module("app.api.v1.endpoints.sessions")
    return database, sessions, state, endpoint


def session_doc(**overrides):
    doc = {
        "_id": ObjectId(), "user_id": USER_ID, "category_id": CREATING["_id"],
        "status": "completed", "tags": "", "notes": "",
        "start_time": NOW - timedelta(hours=2), "end_time": NOW - timedelta(hours=1),
        "elapsed_time": 3600, "updated_at": NOW - timedelta(hours=1),
    }
    doc.update(overrides)
    return doc


def running_doc(**overrides):
    return session_doc(status="active", end_time=None, elapsed_time=None, **overrides)


class SessionEditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db, self.sessions, self.state, self.endpoint = load_modules()
        self.db.sessions_collection.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
        self.db.events_collection.insert_one = AsyncMock()
        self.db.categories_collection.find_one = AsyncMock(side_effect=lambda query: next(
            (category for category in (CREATING, PIANISO) if category["_id"] == query["_id"]), None))
        clock = patch.object(self.sessions, "datetime")
        clock.start().now.return_value = NOW
        self.addCleanup(clock.stop)

    async def edit(self, doc, **changes):
        self.db.sessions_collection.find_one = AsyncMock(return_value=doc)
        return await self.sessions.session_service.update_session(str(USER_ID), str(doc["_id"]), changes)

    def written(self):
        query, update = self.db.sessions_collection.update_one.await_args.args
        return query, update["$set"]

    async def test_new_start_recomputes_elapsed_against_the_saved_end(self):
        result = await self.edit(session_doc(), start_time=NOW - timedelta(hours=3))
        query, written = self.written()
        self.assertEqual(query["updated_at"], NOW - timedelta(hours=1))
        self.assertEqual(written["start_time"], NOW - timedelta(hours=3))
        self.assertEqual(written["elapsed_time"], 2 * 3600)
        self.assertNotIn("end_time", written)
        self.assertNotIn("status", written)
        self.assertEqual(result["elapsed_time"], 2 * 3600)
        self.assertEqual(result["category"]["label"], "Creating")
        self.db.events_collection.insert_one.assert_not_awaited()

    async def test_end_time_on_running_session_clocks_it_out(self):
        result = await self.edit(running_doc(), end_time=NOW - timedelta(minutes=30))
        _, written = self.written()
        self.assertEqual(written["status"], "completed")
        self.assertEqual(written["elapsed_time"], 90 * 60)
        self.assertFalse(result["is_active"])
        event = self.db.events_collection.insert_one.await_args.args[0]
        self.assertEqual((event["event_type"], event["source"]), ("clocked_out", "api"))

    async def test_running_session_start_can_move_and_it_keeps_running(self):
        result = await self.edit(running_doc(), start_time=NOW - timedelta(hours=4))
        _, written = self.written()
        self.assertNotIn("elapsed_time", written)
        self.assertNotIn("status", written)
        self.assertTrue(result["is_active"])

    async def test_rejects_end_before_start_and_future_times(self):
        for changes, message in (
            ({"end_time": NOW - timedelta(hours=3)}, "End time must be after the start time."),
            ({"start_time": NOW + timedelta(minutes=5)}, "Start time can't be in the future."),
            ({"end_time": NOW + timedelta(minutes=5)}, "End time can't be in the future."),
        ):
            with self.subTest(changes=changes), self.assertRaises(self.sessions.SessionUpdateError) as raised:
                await self.edit(session_doc(), **changes)
            self.assertEqual((str(raised.exception), raised.exception.status_code), (message, 422))
        self.db.sessions_collection.update_one.assert_not_awaited()

    async def test_small_browser_clock_skew_is_clamped_to_now(self):
        await self.edit(running_doc(), end_time=NOW + timedelta(seconds=30))
        _, written = self.written()
        self.assertEqual(written["end_time"], NOW)

    async def test_category_change_is_validated_and_tags_trimmed(self):
        for category_id in ("not-an-id", str(ObjectId())):
            with self.subTest(category_id=category_id), self.assertRaises(self.sessions.SessionUpdateError):
                await self.edit(session_doc(), category_id=category_id)
        result = await self.edit(session_doc(), category_id=str(PIANISO["_id"]), tags=" technical ")
        _, written = self.written()
        self.assertEqual(written["category_id"], PIANISO["_id"])
        self.assertEqual(written["tags"], "technical")
        self.assertNotIn("elapsed_time", written)
        self.assertEqual((result["category"]["label"], result["tags"]), ("Pianiso", "technical"))

    async def test_change_made_while_saving_is_reported_not_overwritten(self):
        self.db.sessions_collection.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=0))
        with self.assertRaises(self.sessions.SessionUpdateError) as raised:
            await self.edit(session_doc(), start_time=NOW - timedelta(hours=3))
        self.assertEqual(raised.exception.status_code, 409)

    async def test_missing_or_malformed_session_is_not_found(self):
        service = self.sessions.session_service
        self.assertIsNone(await service.update_session(str(USER_ID), "not-an-id", {}))
        self.db.sessions_collection.find_one = AsyncMock(return_value=None)
        self.assertIsNone(await service.update_session(str(USER_ID), str(ObjectId()), {}))

    def test_request_requires_timezone_aware_times(self):
        with self.assertRaises(ValidationError):
            SessionUpdateRequest(start_time="2026-10-01T10:00:00")
        parsed = SessionUpdateRequest(start_time="2026-10-01T10:00:00Z")
        self.assertEqual(parsed.start_time.utcoffset(), timedelta(0))

    async def test_endpoint_resyncs_buttons_after_success_only(self):
        state_manager = SimpleNamespace(sync_active_session=AsyncMock())
        gpio = SimpleNamespace(sync_led=MagicMock())
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            user_id=USER_ID, state_manager=state_manager, gpio=gpio)))
        changes = SessionUpdateRequest(tags="technical")
        service = self.endpoint.session_service

        with patch.object(service, "update_session", AsyncMock(return_value={"id": "s1"})) as update:
            self.assertEqual(await self.endpoint.update_session(request, "s1", changes), {"id": "s1"})
        update.assert_awaited_once_with(USER_ID, "s1", {"tags": "technical"})
        state_manager.sync_active_session.assert_awaited_once()
        gpio.sync_led.assert_called_once()

        for outcome, status in (
            ({"return_value": None}, 404),
            ({"side_effect": self.sessions.SessionUpdateError("Busy", status_code=409)}, 409),
        ):
            with patch.object(service, "update_session", AsyncMock(**outcome)), \
                    self.assertRaises(HTTPException) as raised:
                await self.endpoint.update_session(request, "s1", changes)
            self.assertEqual(raised.exception.status_code, status)
        state_manager.sync_active_session.assert_awaited_once()

    async def test_sync_reloads_running_session_for_the_next_button_press(self):
        loop = MagicMock()
        manager = self.state.StateManager(loop, USER_ID)
        running = running_doc(category_id=PIANISO["_id"], tags="technical")
        with patch.object(self.state.session_service, "get_active_session", AsyncMock(return_value=running)):
            await manager.sync_active_session()
        self.assertTrue(manager.is_active_session("pianiso", "technical"))
        self.assertFalse(manager.is_active_session("creating"))
        loop.call_soon_threadsafe.assert_called_once()


if __name__ == "__main__":
    unittest.main()
