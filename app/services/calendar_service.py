from datetime import date, datetime, time, timedelta, timezone

from bson import ObjectId

from app.core.database import categories_collection, events_collection, notes_collection, pullups_collection, sessions_collection
from app.schemas.category_schema import category_summary_serial
from app.services.overview_service import OVERVIEW_TIMEZONE
from app.services.pullup_service import group_into_sets

MINUTES_PER_DAY = 24 * 60


def local_midnight(day: date) -> datetime:
  return datetime.combine(day, time(), tzinfo=OVERVIEW_TIMEZONE).astimezone(timezone.utc)


def minute_of_day(moment: datetime) -> float:
  # The wall-clock position in the day, so it lines up with the hour labels.
  local = moment.astimezone(OVERVIEW_TIMEZONE)
  return local.hour * 60 + local.minute + local.second / 60


def split_at_midnight(start: datetime, end: datetime):
  # (local date, segment start, segment end) for each day the span touches.
  current = start
  while current < end:
    day = current.astimezone(OVERVIEW_TIMEZONE).date()
    segment_end = min(end, local_midnight(day + timedelta(days=1)))
    yield day, current, segment_end
    current = segment_end


def distraction_times(events: list[dict], count: int) -> list[datetime]:
  # Replays a session's distraction presses and removals. A removal undoes
  # the latest press. If the count was lowered in the edit dialog, which logs
  # no events, only the latest presses are kept.
  times = []
  for event in events:
    if event["event_type"] == "distraction":
      times.append(event["created_at"])
    elif event["event_type"] == "distraction_removed" and times:
      times.pop()
  return times[-count:] if count < len(times) else times


class CalendarService:
  def __init__(self):
    pass

  async def get_calendar(self, user_id: str, start: date, days: int) -> dict:
    now = datetime.now(timezone.utc)
    range_start = local_midnight(start)
    range_end = local_midnight(start + timedelta(days=days))
    user = ObjectId(user_id)

    sessions = await sessions_collection.find({
      "user_id": user,
      "start_time": {"$lt": range_end},
      "$or": [{"end_time": {"$gte": range_start}}, {"end_time": None}],
    }).sort("start_time", 1).to_list(length=None)
    category_ids = list({session["category_id"] for session in sessions if session.get("category_id")})
    categories = (
      await categories_collection.find({"_id": {"$in": category_ids}}).to_list(length=None)
      if category_ids else []
    )
    category_map = {str(category["_id"]): category for category in categories}
    events = await events_collection.find({
      "session_id": {"$in": [str(session["_id"]) for session in sessions]},
      "event_type": {"$in": ["distraction", "distraction_removed"]},
    }).sort("created_at", 1).to_list(length=None) if sessions else []
    pullups = await pullups_collection.find(
      {"user_id": user, "created_at": {"$gte": range_start, "$lt": range_end}}, {"created_at": 1},
    ).sort("created_at", 1).to_list(length=None)
    notes = await notes_collection.find(
      {"user_id": user, "at": {"$gte": range_start, "$lt": range_end}},
    ).sort("at", 1).to_list(length=None)

    dates = [start + timedelta(days=offset) for offset in range(days)]
    entries = {
      day: {"date": day.isoformat(), "worked_seconds": 0, "categories": {}, "blocks": [], "markers": []}
      for day in dates
    }

    def add_marker(moment: datetime, marker: dict) -> None:
      day = moment.astimezone(OVERVIEW_TIMEZONE).date()
      if day in entries:
        entries[day]["markers"].append({"at": moment, "minute": minute_of_day(moment), **marker})

    events_by_session = {}
    for event in events:
      events_by_session.setdefault(event["session_id"], []).append(event)

    for session in sessions:
      session_id = str(session["_id"])
      running = session.get("end_time") is None
      end = session.get("end_time") or now
      category = category_map.get(str(session.get("category_id")), {})
      summary = category_summary_serial(category) if category else None
      tags = (session.get("tags") or "").strip()
      session_seconds = max(0, int((end - session["start_time"]).total_seconds()))
      for day, segment_start, segment_end in split_at_midnight(session["start_time"], end):
        if day not in entries:
          continue
        entry = entries[day]
        seconds = int((segment_end - segment_start).total_seconds())
        ends_at_midnight = segment_end == local_midnight(day + timedelta(days=1))
        entry["blocks"].append({
          "session_id": session_id,
          "start": segment_start,
          "end": None if running and segment_end == end else segment_end,
          "start_minute": minute_of_day(segment_start),
          "end_minute": MINUTES_PER_DAY if ends_at_midnight else minute_of_day(segment_end),
          "is_active": running and segment_end == end,
          "category": summary,
          "tags": tags,
          "session_start": session["start_time"],
          "session_end": session.get("end_time"),
          "session_seconds": session_seconds,
          "distractions": session.get("distractions", 0),
        })
        entry["worked_seconds"] += seconds
        key = f"{session.get('category_id')}:{tags.lower().replace('-', '_').replace(' ', '_')}"
        breakdown = entry["categories"].setdefault(key, {
          "id": key,
          "label": category.get("label") or "Missing category",
          "color": category.get("color"),
          "tag_colors": category.get("tag_colors") or {},
          "tags": tags,
          "seconds": 0,
          "is_active": False,
        })
        breakdown["seconds"] += seconds
        breakdown["is_active"] = breakdown["is_active"] or (running and segment_end == end)

      for moment in distraction_times(events_by_session.get(session_id, []), session.get("distractions", 0)):
        add_marker(moment, {"kind": "distraction", "session_id": session_id})

    # One marker per set, at its first tap.
    for taps in group_into_sets([pullup["created_at"] for pullup in pullups]):
      add_marker(taps[0], {"kind": "pullups", "count": len(taps)})

    for note in notes:
      add_marker(note["at"], {
        "kind": "note",
        "text": note["text"],
        "session_id": str(note["session_id"]) if note.get("session_id") else None,
      })

    for entry in entries.values():
      entry["categories"] = sorted(entry["categories"].values(), key=lambda item: (-item["seconds"], item["label"]))
      entry["markers"].sort(key=lambda marker: marker["at"])

    return {"start": start.isoformat(), "days": days, "entries": [entries[day] for day in dates]}


calendar_service = CalendarService()
