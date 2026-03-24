import asyncio
from datetime import datetime, timezone
from app.manager import manager
from app.models.sessions import SessionModel
from app.services.session_service import session_service

class StateManager:
  def __init__(self, loop, user_id):
    self.loop = loop
    self.clocked_in = False
    self.started_at = None
    self.user_id = str(user_id)
  
  def is_clocked_in(self) -> bool:
    return self.clocked_in
  
  def get_state(self) -> dict:
    return {
      "clocked_in" : self.clocked_in,
      "started_at" : self.started_at.isoformat() if self.started_at else None
    }
  
  async def restore_active_session(self) -> None:
    active_session = await session_service.get_active_session(self.user_id)
    if not active_session:
      self.clocked_in = False
      self.started_at = None
      return
    
    start_time = active_session["start_time"]
    if start_time.tzinfo is None:
      start_time = start_time.replace(tzinfo=timezone.utc)

    self.clocked_in = True
    self.started_at = start_time

  
  async def clock_in(self) -> None:
    now = datetime.now(timezone.utc)
    await session_service.open_session(self.user_id)
    
    self.clocked_in = True
    self.started_at = now

  async def clock_out(self) -> None:
    await session_service.close_session(self.user_id)

    self.clocked_in = False
    self.started_at = None

  async def toggle(self) -> None:
    if self.clocked_in:
      await self.clock_out()
    else:
      await self.clock_in()
    
    self._broadcast_state()

    # print the status
    if self.clocked_in:
      print("Clocked in")
    else:
      print("Clocked out")

  def _broadcast_state(self) -> None:
    payload = {
      "type": "state_update",
      "data": self.get_state(),
    }

    self.loop.call_soon_threadsafe(
      lambda: asyncio.create_task(manager.broadcast(payload))
    )