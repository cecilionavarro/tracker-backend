from bson import ObjectId
from pymongo import ReturnDocument
from app.models.events import EventModel
from app.models.sessions import SessionModel
from datetime import datetime, timedelta, timezone
from app.core.database import sessions_collection
from app.core.database import events_collection
from app.core.database import categories_collection
from app.services.note_service import note_service
from app.core.config import settings
from app.schemas.category_schema import category_summary_serial
from app.schemas.session_schema import individual_session_serial, list_session_serial

CATEGORY_ALIASES = {
  "GYRUS": "69cb0874185e44b0a39bb520",
  "TOYCON": "69cb0b2c1c51a675c0caee58",
  "CREATING": "69c2eb61c3192568a8a3b370",
  "PIANISO": "6a02b0c85f921debb9421cee",
}

# Allows for a browser clock that runs slightly ahead when someone picks "now".
FUTURE_TOLERANCE = timedelta(minutes=1)

class SessionUpdateError(Exception):
  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code

class SessionService():
  def __init__(self):
    pass

  def _get_session_category_id(self) -> str:
    configured_category = settings.SESSION_CATEGORY.strip()
    return CATEGORY_ALIASES.get(configured_category.upper(), configured_category)

  def resolve_category_id(self, category: str | None = None) -> str:
    if category is None:
      return self._get_session_category_id()

    configured_category = category.strip()
    return CATEGORY_ALIASES.get(configured_category.upper(), configured_category)

  async def get_active_session(self, user_id: str):
    return await sessions_collection.find_one({
      "user_id": ObjectId(user_id),
      "status": "active",
      "end_time": None,
    })

  async def open_session(self, user_id: str, category: str | None = None, tags: str = "") -> str:
    now = datetime.now(timezone.utc)

    session = SessionModel(
      user_id = user_id,
      category_id = self.resolve_category_id(category),
      status = "active",
      start_time=now,
      end_time = None,
      tags = tags,
      notes = "",
      created_at=now,
      updated_at=now
    )

    payload = session.model_dump(exclude={"id"})
    payload["user_id"] = ObjectId(payload["user_id"])
    payload["category_id"] = ObjectId(payload["category_id"])
    # session.user_id = ObjectId(session.user_id)
    # session.category_id = ObjectId(session.category_id)

    returned_session = await sessions_collection.insert_one(payload)

    event = EventModel(
      session_id = str(returned_session.inserted_id),
      event_type = "clocked_in",
      source = "raspberry_pi",
      created_at = now,
    )

    await events_collection.insert_one(event.model_dump(exclude={"id"}))
    return str(returned_session.inserted_id)


  async def close_session(self, user_id):
    now = datetime.now(timezone.utc)

    active_session = await self.get_active_session(user_id)

    # if can't find it in db
    if not active_session:
      return

    elapsed_time = int((now - active_session["start_time"]).total_seconds())
    
    updated_session = {
      "status" : "completed",
      "end_time" : now,
      "elapsed_time" : elapsed_time,
      "updated_at": now,
    }

    # update_one(filter, update)
    # $set means update these value fields
    await sessions_collection.update_one(
        {"_id": active_session["_id"]},
        {
          "$set" : updated_session
        }
      )

    event = EventModel(
      session_id = str(active_session["_id"]),
      event_type = "clocked_out",
      source = "raspberry_pi",
      created_at = now,
    )

    await events_collection.insert_one(event.model_dump(exclude={"id"}))

  async def close_session_by_id(self, user_id: str, session_id: str) -> dict | None:
    now = datetime.now(timezone.utc)

    session = await sessions_collection.find_one({
      "_id": ObjectId(session_id),
      "user_id": ObjectId(user_id),
    })

    if not session:
      return None

    if session.get("status") == "active" and session.get("end_time") is None:
      elapsed_time = int((now - session["start_time"]).total_seconds())
      updated_session = {
        "status": "completed",
        "end_time": now,
        "elapsed_time": elapsed_time,
        "updated_at": now,
      }

      await sessions_collection.update_one(
        {"_id": session["_id"]},
        {"$set": updated_session},
      )

      event = EventModel(
        session_id=str(session["_id"]),
        event_type="clocked_out",
        source="api",
        created_at=now,
      )
      await events_collection.insert_one(event.model_dump(exclude={"id"}))

      session.update(updated_session)

    return session

  async def delete_session(self, user_id: str, session_id: str) -> dict | None:
    session = await sessions_collection.find_one({
      "_id": ObjectId(session_id),
      "user_id": ObjectId(user_id),
    })

    if not session:
      return None

    was_active = session.get("status") == "active" and session.get("end_time") is None

    session = await self.close_session_by_id(user_id, session_id)

    if not session:
      return None

    await sessions_collection.delete_one({
      "_id": session["_id"],
      "user_id": ObjectId(user_id),
    })
    await events_collection.delete_many({"session_id": str(session["_id"])})
    await note_service.detach_session(session["_id"])

    return {
      "id": str(session["_id"]),
      "was_active": was_active,
    }

  async def update_session(self, user_id: str, session_id: str, changes: dict) -> dict | None:
    if not ObjectId.is_valid(session_id):
      return None

    session = await sessions_collection.find_one({
      "_id": ObjectId(session_id),
      "user_id": ObjectId(user_id),
    })

    if not session:
      return None

    now = datetime.now(timezone.utc)
    was_active = session.get("status") == "active" and session.get("end_time") is None
    updates = {"updated_at": now}

    for field, label in (("start_time", "Start"), ("end_time", "End")):
      if field not in changes:
        continue

      value = changes[field].astimezone(timezone.utc)
      if value > now + FUTURE_TOLERANCE:
        raise SessionUpdateError(f"{label} time can't be in the future.")
      updates[field] = min(value, now)

    start_time = updates.get("start_time", session["start_time"])
    end_time = updates.get("end_time", session.get("end_time"))

    if end_time is not None and end_time <= start_time:
      raise SessionUpdateError("End time must be after the start time.")

    if end_time is not None and ("start_time" in updates or "end_time" in updates):
      updates["elapsed_time"] = int((end_time - start_time).total_seconds())

    # Giving a running session an end time clocks it out.
    if was_active and "end_time" in updates:
      updates["status"] = "completed"

    category = None
    if "category_id" in changes:
      category_id = changes["category_id"]
      if ObjectId.is_valid(category_id):
        category = await categories_collection.find_one({"_id": ObjectId(category_id)})
      if not category:
        raise SessionUpdateError("Unknown category.")
      updates["category_id"] = category["_id"]

    if "tags" in changes:
      updates["tags"] = changes["tags"].strip()

    if "distractions" in changes:
      updates["distractions"] = changes["distractions"]

    # Matching updated_at skips the write if a button press changed this
    # session after it was read, instead of mixing old and new times.
    result = await sessions_collection.update_one(
      {
        "_id": session["_id"],
        "user_id": ObjectId(user_id),
        "updated_at": session.get("updated_at"),
      },
      {"$set": updates},
    )

    if result.matched_count == 0:
      raise SessionUpdateError("This session changed while saving. Please try again.", status_code=409)

    if updates.get("status") == "completed":
      event = EventModel(
        session_id=str(session["_id"]),
        event_type="clocked_out",
        source="api",
        created_at=now,
      )
      await events_collection.insert_one(event.model_dump(exclude={"id"}))

    session.update(updates)

    if not category:
      category = await categories_collection.find_one({"_id": session["category_id"]})
    session["category"] = category_summary_serial(category)

    return individual_session_serial(session)

  async def change_distractions(self, user_id: str, amount: int, source: str) -> dict | None:
    # Adds (or with a negative amount, removes) distractions on the running
    # session in one atomic update, so quick presses are never lost.
    # Returns None when no session is running.
    now = datetime.now(timezone.utc)
    query = {
      "user_id": ObjectId(user_id),
      "status": "active",
      "end_time": None,
    }
    if amount < 0:
      # Never count below zero.
      query["distractions"] = {"$gte": -amount}

    session = await sessions_collection.find_one_and_update(
      query,
      {"$inc": {"distractions": amount}, "$set": {"updated_at": now}},
      return_document=ReturnDocument.AFTER,
    )

    if not session:
      active_session = await self.get_active_session(user_id) if amount < 0 else None
      if not active_session:
        return None
      # Already at zero: nothing to remove.
      return {
        "session_id": str(active_session["_id"]),
        "distractions": active_session.get("distractions", 0),
      }

    event = EventModel(
      session_id=str(session["_id"]),
      event_type="distraction" if amount > 0 else "distraction_removed",
      source=source,
      created_at=now,
    )
    await events_collection.insert_one(event.model_dump(exclude={"id"}))

    return {
      "session_id": str(session["_id"]),
      "distractions": session["distractions"],
    }

  async def list_sessions(self, user_id: str, page: int = 1, page_size: int = 10):
    skip = (page - 1) * page_size
    query = {"user_id": ObjectId(user_id)}                    # filter

    total = await sessions_collection.count_documents(query)  # how many documents fit this filter

    # building the cursor, how to get the data like where to start how many to skip, what num of documents to return.
    # equivalent to `sessions = await sessions_collection.find(query).sort("start_time", -1).skip(skip).limit(page_size).to_list(length=page_size)`
    cursor = (
      sessions_collection
      .find(query)
      .sort("start_time", -1)
      .skip(skip)
      .limit(page_size)
    )

    sessions = await cursor.to_list(length=page_size)         # to list converts to list :)

    # new
    category_ids = list({session["category_id"] for session in sessions if session.get("category_id")})
    category_map = {}
    if category_ids:
      categories = await categories_collection.find({"_id": {"$in": category_ids}}).to_list(length=len(category_ids))

      print(categories)

      category_map = {
        str(category["_id"]): {
          "id": str(category["_id"]),
          "label": category["label"],
          "color": category.get("color"),
          "tag_colors": category.get("tag_colors") or {},
        }
        for category in categories
      }
      for session in sessions:
        category_id = session.get("category_id")
        session["category"] = category_map.get(str(category_id)) if category_id else None

    # end new

    # Each session's note count and most recent note.
    note_summary = await note_service.summarize_sessions([session["_id"] for session in sessions])
    for session in sessions:
      summary = note_summary.get(str(session["_id"]), {})
      session["note_count"] = summary.get("count", 0)
      session["latest_note"] = summary.get("latest", "")

    items = list_session_serial(sessions)

    total_pages = (total + page_size -1) // page_size

    return {
      "items": items,
      "total": total,
      "page": page,
      "page_size": page_size,
      "total_pages": total_pages,
    }


session_service = SessionService()
