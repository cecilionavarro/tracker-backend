from app.models.events import EventModel
from app.models.sessions import SessionModel
from datetime import datetime, timezone
from app.core.database import sessions_collection
from app.core.database import events_collection

class SessionService():
  def __init__(self):
    pass

  async def open_session(self, user_id: str) -> str:
    now = datetime.now(timezone.utc)

    session = SessionModel(
      user_id = user_id,
      status = "active",
      start_time=now,
      end_time = None,
      notes = "",
    )

    returned_session = await sessions_collection.insert_one(session.model_dump(exclude={"id"}))

    event = EventModel(
      session_id = str(returned_session.inserted_id),
      event_type = "clocked_in",
      source = "button_press",
      timestamp = now,
    )

    await events_collection.insert_one(event.model_dump(exclude={"id"}))
    return str(returned_session.inserted_id)


  async def close_session(self, user_id):
    now = datetime.now(timezone.utc)

    active_session = await sessions_collection.find_one({
      "user_id": user_id,
      "status": "active",
      "end_time": None,
    })

    if active_session:
      updated_session = {
        "status" : "completed",
        "end_time" : now,
      }
    else:
      return

    await sessions_collection.update_one(
        {"_id": active_session["_id"]},
        {
          "$set" : updated_session
        }
      )

    event = EventModel(
      session_id = str(active_session["_id"]),
      event_type = "clocked_out",
      source = "button_press",
      timestamp = now,
    )

    await events_collection.insert_one(event.model_dump(exclude={"id"}))

session_service = SessionService()