import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import WebSocketDisconnect

from app.manager import ConnectionManager
from app.api.v1.websockets.dashboard import dashboard_websocket


class DashboardWebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_dead_client_does_not_block_healthy_clients(self):
        manager = ConnectionManager()
        dead = SimpleNamespace(send_json=AsyncMock(side_effect=WebSocketDisconnect()),
                               close=AsyncMock())
        healthy = SimpleNamespace(send_json=AsyncMock())
        manager.active_connections = [dead, healthy]
        payload = {"type": "state_update"}
        await manager.broadcast(payload)
        healthy.send_json.assert_awaited_once_with(payload)
        self.assertEqual(manager.active_connections, [healthy])

    async def test_slow_client_does_not_delay_healthy_send(self):
        manager = ConnectionManager()
        release = asyncio.Event()
        delivered = asyncio.Event()

        async def blocked(_):
            await release.wait()

        async def receive(_):
            delivered.set()

        slow = SimpleNamespace(send_json=blocked)
        healthy = SimpleNamespace(send_json=receive)
        manager.active_connections = [slow, healthy]
        task = asyncio.create_task(manager.broadcast({"type": "state_update"}))
        try:
            await asyncio.wait_for(delivered.wait(), timeout=0.5)
            self.assertFalse(task.done())
        finally:
            release.set()
            await task

    async def test_ping_replies_only_to_sender_and_disconnect_cleans_up(self):
        manager = ConnectionManager()
        state = {"clocked_in": True}
        socket = SimpleNamespace(
            accept=AsyncMock(), send_json=AsyncMock(),
            receive_json=AsyncMock(side_effect=[{"type": "ping"}, WebSocketDisconnect()]),
            app=SimpleNamespace(state=SimpleNamespace(
                state_manager=SimpleNamespace(get_state=lambda: state))),
        )
        with patch("app.api.v1.websockets.dashboard.manager", manager):
            await dashboard_websocket(socket)
        self.assertEqual([call.args[0]["type"] for call in socket.send_json.await_args_list],
                         ["status_update", "pong"])
        self.assertEqual(manager.active_connections, [])

    async def test_initial_send_failure_cleans_up_connection(self):
        manager = ConnectionManager()
        socket = SimpleNamespace(
            accept=AsyncMock(), send_json=AsyncMock(side_effect=WebSocketDisconnect()),
            app=SimpleNamespace(state=SimpleNamespace(
                state_manager=SimpleNamespace(get_state=lambda: {}))),
        )
        with patch("app.api.v1.websockets.dashboard.manager", manager):
            await dashboard_websocket(socket)
        self.assertEqual(manager.active_connections, [])


if __name__ == "__main__":
    unittest.main()
