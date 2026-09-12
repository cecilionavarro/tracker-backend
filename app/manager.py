import asyncio
import logging
from typing import List
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

class ConnectionManager:
  def __init__(self):
    self.active_connections: List[WebSocket] = []
  
  async def connect(self, websocket: WebSocket):
    await websocket.accept()
    self.active_connections.append(websocket)
  
  def disconnect(self, websocket: WebSocket):
    if websocket in self.active_connections:
      self.active_connections.remove(websocket)
  
  async def broadcast(self, payload: dict):
    async def send(connection):
      try:
        await asyncio.wait_for(connection.send_json(payload), timeout=5)
      except (WebSocketDisconnect, OSError, RuntimeError, TimeoutError):
        self.disconnect(connection)
        logger.info("Removed disconnected or unresponsive dashboard client")
        try:
          await asyncio.wait_for(connection.close(), timeout=1)
        except (WebSocketDisconnect, OSError, RuntimeError, TimeoutError):
          pass

    # Snapshot because disconnect handlers may modify the live list during sends.
    # A slow/closed client must not hold up updates to other browsers.
    await asyncio.gather(*(send(connection) for connection in tuple(self.active_connections)))

manager = ConnectionManager()
