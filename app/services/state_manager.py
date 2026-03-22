import asyncio
from datetime import datetime, timezone
from app.manager import manager

class StateManager:
  def __init__(self, loop):
    self.loop = loop
    self.clocked_in = False
    self.started_at = None
  
  def is_clocked_in(self) -> bool:
    return self.clocked_in
  
  def get_state(self) -> dict:
    return {
      "clocked_in" : self.clocked_in,
      "started_at" : self.started_at.isoformat() if self.started_at else None
    }
  
  def clock_in(self) -> None:
    self.clocked_in = True
    self.started_at = datetime.now(timezone.utc)

  def clock_out(self) -> None:
    self.clocked_in = False
    self.started_at = None

  def toggle(self) -> None:
    if self.clocked_in:
      self.clock_out()
    else:
      self.clock_in()
    
    self._broadcast_state()
    # print(self.clocked_in)
    # print(self.started_at)

  def _broadcast_state(self) -> None:
    payload = {
      "type": "state_update",
      "data": self.get_state(),
    }

    self.loop.call_soon_threadsafe(
      lambda: asyncio.create_task(manager.broadcast(payload))
    )