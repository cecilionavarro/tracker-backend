from bson import ObjectId
from app.models.events import EventModel
from app.models.sessions import SessionModel
from datetime import datetime, timezone
from app.core.database import sessions_collection
from app.core.database import events_collection

class SessionService():
  def __init__(self):
    pass

  async def get_active_session(self, user_id: str):
    return await sessions_collection.find_one({
      "user_id": ObjectId(user_id),
      "status": "active",
      "end_time": None,
    })

  async def open_session(self, user_id: str) -> str:
    now = datetime.now(timezone.utc)

    session = SessionModel(
      user_id = user_id,
      category_id = "69c2af380b699d12ba42404b",
      status = "active",
      start_time=now,
      end_time = None,
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

    active_session = await sessions_collection.find_one({
      "user_id": ObjectId(user_id),
      "status": "active",
      "end_time": None,
    })

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

session_service = SessionService()