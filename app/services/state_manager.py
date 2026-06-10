import asyncio
from datetime import datetime, timezone
from app.manager import manager
from app.services.session_service import session_service

class StateManager:
  def __init__(self, loop, user_id):
    self.loop = loop
    self.clocked_in = False
    self.started_at = None
    self.user_id = str(user_id)
    self.active_category_id = None
    self.active_tags = ""

  def _normalize_tags(self, tags: str | None) -> str:
    return (tags or "").strip()

  def _set_active_session_metadata(self, category_id: str | None, tags: str | None) -> None:
    self.active_category_id = str(category_id) if category_id else None
    self.active_tags = self._normalize_tags(tags)
    
  def is_clocked_in(self) -> bool:
    return self.clocked_in

  def is_active_session(self, category: str, tags: str = "") -> bool:
    return (
      self.clocked_in
      and self.active_category_id == session_service.resolve_category_id(category)
      and self.active_tags == self._normalize_tags(tags)
    )
  
  def get_state(self) -> dict:
    return {
      "clocked_in" : self.clocked_in,
      "started_at" : self.started_at.isoformat() if self.started_at else None,
      "category_id": self.active_category_id,
      "tags": self.active_tags,
    }
  
  async def restore_active_session(self) -> None:
    active_session = await session_service.get_active_session(self.user_id)
    
    if not active_session:
      self.clocked_in = False
      self.started_at = None
      self._set_active_session_metadata(None, "")
      print("Clocked out (db)")
      return
    
    print("Clocked in (db)")
    start_time = active_session["start_time"]
    if start_time.tzinfo is None:
      start_time = start_time.replace(tzinfo=timezone.utc)

    self.clocked_in = True
    self.started_at = start_time
    self._set_active_session_metadata(active_session.get("category_id"), active_session.get("tags", ""))

  
  async def clock_in(self, category: str | None = None, tags: str = "") -> None:
    now = datetime.now(timezone.utc)
    category_id = session_service.resolve_category_id(category)
    normalized_tags = self._normalize_tags(tags)
    await session_service.open_session(self.user_id, category=category, tags=normalized_tags)
    
    self.clocked_in = True
    self.started_at = now
    self._set_active_session_metadata(category_id, normalized_tags)

  async def clock_out(self) -> None:
    await session_service.close_session(self.user_id)

    self.clocked_in = False
    self.started_at = None
    self._set_active_session_metadata(None, "")

  async def toggle(self) -> None:
    if self.is_clocked_in():
      await self.clock_out()
    else:
      await self.clock_in()
    
    self._broadcast_state()

    # print the status
    if self.is_clocked_in():
      print("Clocked in")
    else:
      print("Clocked out")

  async def toggle_activity(self, category: str, tags: str = "") -> None:
    if self.is_active_session(category, tags):
      await self.clock_out()
      print(f"Clocked out of {category} ({self._normalize_tags(tags) or 'default'})")
    else:
      if self.is_clocked_in():
        await self.clock_out()

      await self.clock_in(category=category, tags=tags)
      print(f"Clocked into {category} ({self.active_tags or 'default'})")

    self._broadcast_state()

  async def clear_active_session(self) -> None:
    self.clocked_in = False
    self.started_at = None
    self._set_active_session_metadata(None, "")
    self._broadcast_state()

  def _broadcast_state(self) -> None:
    payload = {
      "type": "state_update",
      "data": self.get_state(),
    }

    self.loop.call_soon_threadsafe(
      lambda: asyncio.create_task(manager.broadcast(payload))
    )
