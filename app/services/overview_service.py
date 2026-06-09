from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.core.database import sessions_collection


OVERVIEW_TIMEZONE = ZoneInfo("America/Los_Angeles")
DAILY_GOAL_SECONDS = 8 * 60 * 60


class OverviewService:
    def __init__(self):
        pass

    async def _get_active_session(self, user_id: str):
        return await sessions_collection.find_one({
            "user_id": ObjectId(user_id),
            "status": "active",
            "end_time": None,
        })

    def _get_session_end(self, session: dict, now: datetime) -> datetime:
        return session.get("end_time") or now

    def _get_full_session_duration_seconds(self, session: dict, now: datetime) -> int:
        end_time = self._get_session_end(session, now)
        return max(int((end_time - session["start_time"]).total_seconds()), 0)

    def _get_session_overlap_seconds(
        self,
        session: dict,
        range_start: datetime,
        range_end: datetime,
        now: datetime,
    ) -> int:
        session_start = session["start_time"]
        session_end = self._get_session_end(session, now)

        overlap_start = max(session_start, range_start)
        overlap_end = min(session_end, range_end)

        if overlap_end <= overlap_start:
            return 0

        return int((overlap_end - overlap_start).total_seconds())

    def _split_session_by_local_day(self, session: dict, now: datetime) -> list[dict]:
        start_utc = session["start_time"]
        end_utc = self._get_session_end(session, now)

        if end_utc <= start_utc:
            return []

        start_local = start_utc.astimezone(OVERVIEW_TIMEZONE)
        end_local = end_utc.astimezone(OVERVIEW_TIMEZONE)

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

    async def get_overview(self, user_id: str):
        now = datetime.now(timezone.utc)
        now_local = now.astimezone(OVERVIEW_TIMEZONE)

        start_of_today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_tomorrow_local = start_of_today_local + timedelta(days=1)

        weekday_index = start_of_today_local.weekday()  # Monday = 0
        start_of_week_local = start_of_today_local - timedelta(days=weekday_index)
        end_of_week_local = start_of_week_local + timedelta(days=7)

        start_of_today_utc = start_of_today_local.astimezone(timezone.utc)
        start_of_tomorrow_utc = start_of_tomorrow_local.astimezone(timezone.utc)
        start_of_week_utc = start_of_week_local.astimezone(timezone.utc)
        end_of_week_utc = end_of_week_local.astimezone(timezone.utc)

        week_sessions = await sessions_collection.find({
            "user_id": ObjectId(user_id),
            "start_time": {
                "$lt": end_of_week_utc,
            },
            "$or": [
                {"end_time": {"$gte": start_of_week_utc}},
                {"end_time": None},
            ],
        }).to_list(length=None)

        day_sessions = await sessions_collection.find({
            "user_id": ObjectId(user_id),
            "start_time": {
                "$gte": start_of_today_utc,
                "$lt": start_of_tomorrow_utc,
            },
        }).sort("start_time", 1).to_list(length=None)

        active_session = await self._get_active_session(user_id)

        day_segments = []
        week_graph = []
        goal_completed_days = 0
        week_total_seconds = 0

        for offset in range(7):
            current_day_local = start_of_week_local + timedelta(days=offset)
            current_date = current_day_local.date()
            is_future = current_date > now_local.date()

            segments_for_day = []

            if not is_future:
                for session in week_sessions:
                    session_segments = self._split_session_by_local_day(session, now)
                    for segment in session_segments:
                        if segment["date"] == current_date:
                            segments_for_day.append(segment)

            seconds = sum(segment["seconds"] for segment in segments_for_day)

            if current_date == now_local.date():
                day_segments = segments_for_day

            if not is_future:
                week_total_seconds += seconds

            goal_met = seconds >= DAILY_GOAL_SECONDS if not is_future else False
            if goal_met:
                goal_completed_days += 1

            week_graph.append({
                "day": current_day_local.strftime("%a")[0],
                "seconds": 0 if is_future else seconds,
                "goal_met": goal_met,
                "is_future": is_future,
            })

        days_elapsed = weekday_index + 1

        week_counted_sessions = [
            session for session in week_sessions
            if self._get_session_overlap_seconds(session, start_of_week_utc, end_of_week_utc, now) > 0
        ]

        week_longest_session_seconds = max(
            (
                self._get_session_overlap_seconds(session, start_of_week_utc, end_of_week_utc, now)
                for session in week_counted_sessions
            ),
            default=0,
        )

        return {
            "day": {
                "status": "clocked_in" if active_session else "clocked_out",
                "longest_session_seconds": max(
                    (segment["seconds"] for segment in day_segments),
                    default=0,
                ),
                "session_count": len(day_sessions),
                "first_session_at": day_sessions[0]["start_time"] if day_sessions else None,
                "goal_seconds": DAILY_GOAL_SECONDS,
                "worked_seconds": sum(segment["seconds"] for segment in day_segments),
                "active_session": (
                    {
                        "id": str(active_session["_id"]),
                        "start_time": active_session["start_time"],
                    }
                    if active_session else None
                ),
            },
            "week": {
                "total_time_seconds": week_total_seconds,
                "longest_session_seconds": week_longest_session_seconds,
                "session_count": len(week_counted_sessions),
                "daily_average_seconds": int(week_total_seconds / days_elapsed) if days_elapsed else 0,
                "goal_completed_days": goal_completed_days,
                "graph": week_graph,
            },
        }


overview_service = OverviewService()
