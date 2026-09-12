from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.manager import manager

router = APIRouter()

@router.websocket("/ws/dashboard/")
async def dashboard_websocket(websocket: WebSocket):
  await manager.connect(websocket)

  try:
    state_manager = websocket.app.state.state_manager
    await websocket.send_json({
      "type": "status_update",
      "data": state_manager.get_state()
    })

    while True:
      try:
        data = await websocket.receive_json()
      except ValueError:
        continue
      if isinstance(data, dict) and data.get("type") == "ping":
        # Reply only to the caller; heartbeats are not dashboard state changes.
        await websocket.send_json({"type": "pong"})
  except (WebSocketDisconnect, OSError):
    pass
  finally:
    manager.disconnect(websocket)
