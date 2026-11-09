from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.core.database import categories_collection, notes_collection, pullups_collection, sessions_collection
from app.schemas.category_schema import category_summary_serial
from app.services.note_service import note_serial
from app.services.overview_service import OVERVIEW_TIMEZONE, overview_service


class WorklogService:
    def __init__(self):
        pass

    def _local_date(self, moment: datetime):
        return moment.astimezone(OVERVIEW_TIMEZONE).date()

    async def get_worklog(self, user_id: str, days: int) -> dict:
        now = datetime.now(timezone.utc)
        today = now.astimezone(OVERVIEW_TIMEZONE).date()
        first_day = today - timedelta(days=days - 1)
        start_utc = datetime.combine(first_day, datetime.min.time(), tzinfo=OVERVIEW_TIMEZONE).astimezone(timezone.utc)
        end_utc = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=OVERVIEW_TIMEZONE).astimezone(timezone.utc)

        sessions = await sessions_collection.find({
            "user_id": ObjectId(user_id),
            "start_time": {"$lt": end_utc},
            "$or": [{"end_time": {"$gte": start_utc}}, {"end_time": None}],
        }).sort("start_time", 1).to_list(length=None)
        notes = await notes_collection.find({
            "user_id": ObjectId(user_id),
            "at": {"$gte": start_utc, "$lt": end_utc},
        }).sort("at", 1).to_list(length=None)
        pullups = await pullups_collection.find(
            {"user_id": ObjectId(user_id), "created_at": {"$gte": start_utc, "$lt": end_utc}},
            {"created_at": 1},
        ).to_list(length=None)

        category_ids = list({session["category_id"] for session in sessions if session.get("category_id")})
        categories = (
            await categories_collection.find({"_id": {"$in": category_ids}}).to_list(length=None)
            if category_ids else []
        )
        category_map = {str(category["_id"]): category for category in categories}

        days_by_date = {}

        def day_for(date):
            return days_by_date.setdefault(date, {
                "date": date.isoformat(), "worked_seconds": 0, "session_count": 0, "pullups": 0,
                "sessions": [], "notes": [],
            })

        # Day totals split sessions at midnight, matching the overview.
        for session in sessions:
            for segment in overview_service._split_session_by_local_day(session, now):
                if first_day <= segment["date"] <= today:
                    day_for(segment["date"])["worked_seconds"] += segment["seconds"]

        notes_by_session = {}
        for note in notes:
            if note.get("session_id"):
                notes_by_session.setdefault(str(note["session_id"]), []).append(note)

        listed_sessions = set()
        for session in sessions:
            # A session is listed on the day it started.
            start_date = self._local_date(session["start_time"])
            if not first_day <= start_date <= today:
                continue
            session_id = str(session["_id"])
            listed_sessions.add(session_id)
            end_time = session.get("end_time")
            day = day_for(start_date)
            day["session_count"] += 1
            day["sessions"].append({
                "id": session_id,
                "start_time": session["start_time"],
                "end_time": end_time,
                "is_active": end_time is None,
                "seconds": max(0, int(((end_time or now) - session["start_time"]).total_seconds())),
                "category": category_summary_serial(category_map.get(str(session.get("category_id")))),
                "tags": session.get("tags", ""),
                "distractions": session.get("distractions", 0),
                "notes": [note_serial(note) for note in notes_by_session.get(session_id, [])],
            })

        # Notes outside any listed session stand alone on their own day.
        for note in notes:
            if note.get("session_id") and str(note["session_id"]) in listed_sessions:
                continue
            day_for(self._local_date(note["at"]))["notes"].append(note_serial(note))

        # Pull-ups count toward the day they were done.
        for pullup in pullups:
            day_for(self._local_date(pullup["created_at"]))["pullups"] += 1

        return {
            "days": days,
            "entries": [
                days_by_date[date] for date in sorted(days_by_date, reverse=True)
                if days_by_date[date]["sessions"] or days_by_date[date]["notes"] or days_by_date[date]["pullups"]
            ],
        }


worklog_service = WorklogService()
