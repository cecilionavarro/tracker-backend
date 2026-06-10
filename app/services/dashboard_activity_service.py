from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.core.database import sessions_collection


DASHBOARD_TIMEZONE = ZoneInfo("America/Los_Angeles")


class DashboardActivityService:
    def __init__(self):
        pass

    def _get_session_end(self, session: dict, now: datetime) -> datetime:
        return session.get("end_time") or now

    def _split_session_by_local_day(self, session: dict, now: datetime) -> list[dict]:
        start_utc = session["start_time"]
        end_utc = self._get_session_end(session, now)

        if end_utc <= start_utc:
            return []

        start_local = start_utc.astimezone(DASHBOARD_TIMEZONE)
        end_local = end_utc.astimezone(DASHBOARD_TIMEZONE)

        segments = []
        current_start = start_local

        while current_start < end_local:
            next_midnight = (current_start + timedelta(days=1)).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            current_end = min(end_local, next_midnight)

            segments.append({
                "date": current_start.date(),
                "seconds": int((current_end - current_start).total_seconds()),
            })

            current_start = current_end

        return segments

    async def get_activity(self, user_id: str, days: int):
        now = datetime.now(timezone.utc)
        now_local = now.astimezone(DASHBOARD_TIMEZONE)

        end_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        start_day_local = end_day_local - timedelta(days=days - 1)
        end_exclusive_local = end_day_local + timedelta(days=1)

        start_utc = start_day_local.astimezone(timezone.utc)
        end_exclusive_utc = end_exclusive_local.astimezone(timezone.utc)

        sessions = await sessions_collection.find({
            "user_id": ObjectId(user_id),
            "start_time": {"$lt": end_exclusive_utc},
            "$or": [
                {"end_time": {"$gte": start_utc}},
                {"end_time": None},
            ],
        }).to_list(length=None)

        activity_by_date = {
            (start_day_local + timedelta(days=offset)).date(): {
                "time_worked": 0,
                "session_ids": set(),
            }
            for offset in range(days)
        }

        for session in sessions:
            session_id = str(session["_id"])

            for segment in self._split_session_by_local_day(session, now):
                segment_date = segment["date"]

                if start_day_local.date() <= segment_date <= end_day_local.date():
                    activity_by_date[segment_date]["time_worked"] += segment["seconds"]
                    activity_by_date[segment_date]["session_ids"].add(session_id)

        points = []

        for offset in range(days):
            current_day_local = start_day_local + timedelta(days=offset)
            current_date = current_day_local.date()
            activity = activity_by_date[current_date]

            points.append({
                "date": current_date.isoformat(),
                "time_worked": activity["time_worked"],
                "session_count": len(activity["session_ids"]),
            })

        return {
            "days": days,
            "points": points,
        }


dashboard_activity_service = DashboardActivityService()