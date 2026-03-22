from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.manager import manager

router = APIRouter()

@router.websocket("/ws/dashboard/")
async def dashboard_websocket(websocket: WebSocket):
  await manager.connect(websocket)

  state_manager = websocket.app.state.state_manager
  
  await websocket.send_json({
    "type" : "status_update",
    "data": state_manager.get_state()
  })

  try:
    while True:
      data = await websocket.receive_json()
      print(data)
      await manager.broadcast(f"Client says: {data}")
  except WebSocketDisconnect:
    manager.disconnect(websocket)
    await manager.broadcast(f"client has disconnected")