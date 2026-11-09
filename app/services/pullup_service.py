from datetime import date, datetime, time, timedelta, timezone

from bson import ObjectId

from app.core.database import pullups_collection
from app.models.pullups import PullupModel
from app.services.overview_service import OVERVIEW_TIMEZONE

# Each rep is one press, tapped out right after the set. Taps less than this
# far apart are one set; a pause longer than this, even a short rest, starts the
# next set.
SET_GAP = timedelta(seconds=3)


def group_into_sets(times: list[datetime]) -> list[list[datetime]]:
  # Each set's tap times, oldest set first.
  sets = []
  previous = None
  for moment in sorted(times):
    if previous is None or moment - previous > SET_GAP:
      sets.append([])
    sets[-1].append(moment)
    previous = moment
  return sets


def split_into_sets(times: list[datetime]) -> list[int]:
  # The number of pull-ups in each set, oldest set first.
  return [len(taps) for taps in group_into_sets(times)]


def get_streak_days(active_dates: set[date], today: date) -> int:
  # Days in a row with pull-ups. A streak stays alive until today ends,
  # so it counts back from yesterday when today has none yet.
  day = today if today in active_dates else today - timedelta(days=1)
  streak = 0
  while day in active_dates:
    streak += 1
    day -= timedelta(days=1)
  return streak


class PullupService:
  def __init__(self):
    pass

  def _start_of_today(self, now: datetime) -> datetime:
    # "Today" matches the dashboard overview's timezone.
    local_midnight = now.astimezone(OVERVIEW_TIMEZONE).replace(
      hour=0, minute=0, second=0, microsecond=0,
    )
    return local_midnight.astimezone(timezone.utc)

  def _today_query(self, user_id: str, now: datetime) -> dict:
    return {
      "user_id": ObjectId(user_id),
      "created_at": {"$gte": self._start_of_today(now)},
    }

  async def add_pullup(self, user_id: str, source: str) -> int:
    now = datetime.now(timezone.utc)
    pullup = PullupModel(user_id=user_id, source=source, created_at=now)

    payload = pullup.model_dump(exclude={"id"})
    payload["user_id"] = ObjectId(payload["user_id"])
    await pullups_collection.insert_one(payload)

    return await pullups_collection.count_documents(self._today_query(user_id, now))

  async def remove_last_pullup(self, user_id: str) -> int | None:
    # Undo only reaches today's pull-ups, the count the dashboard shows.
    # Returns None when there is nothing to undo.
    now = datetime.now(timezone.utc)
    query = self._today_query(user_id, now)

    removed = await pullups_collection.find_one_and_delete(
      query,
      sort=[("created_at", -1)],
    )
    if not removed:
      return None

    return await pullups_collection.count_documents(query)

  def _local_midnight(self, day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=OVERVIEW_TIMEZONE).astimezone(timezone.utc)

  async def get_stats(self, user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(OVERVIEW_TIMEZONE)
    today = local_now.date()
    week_start_date = today - timedelta(days=today.weekday())  # Monday

    start_of_today = self._local_midnight(today)
    start_of_week = self._local_midnight(week_start_date)
    start_of_last_week = self._local_midnight(week_start_date - timedelta(days=7))
    # The same weekday and clock time last week, for a fair comparison.
    same_point_last_week = datetime.combine(
      today - timedelta(days=7), local_now.time(), tzinfo=OVERVIEW_TIMEZONE,
    ).astimezone(timezone.utc)

    recent = await pullups_collection.find(
      {"user_id": ObjectId(user_id), "created_at": {"$gte": start_of_last_week}},
      {"created_at": 1},
    ).sort("created_at", 1).to_list(length=None)
    times = [pullup["created_at"] for pullup in recent]
    today_times = [moment for moment in times if moment >= start_of_today]
    week_times = [moment for moment in times if moment >= start_of_week]
    last_week_times = [moment for moment in times if moment < start_of_week]

    # Daily totals for all time, counted by MongoDB so only one row per day returns.
    cursor = await pullups_collection.aggregate([
      {"$match": {"user_id": ObjectId(user_id)}},
      {"$group": {
        "_id": {"$dateToString": {
          "format": "%Y-%m-%d", "date": "$created_at", "timezone": OVERVIEW_TIMEZONE.key,
        }},
        "count": {"$sum": 1},
      }},
    ])
    daily = {
      date.fromisoformat(row["_id"]): row["count"]
      for row in await cursor.to_list(length=None)
    }
    # Most pull-ups wins; on a tie, the more recent day.
    best_day = max(daily.items(), key=lambda item: (item[1], item[0]), default=None)

    # The most recent set, however long ago. Two weeks of taps usually covers
    # it; otherwise fetch the hour leading up to the latest tap.
    last_times = times
    if not last_times:
      latest = await pullups_collection.find_one(
        {"user_id": ObjectId(user_id)}, {"created_at": 1}, sort=[("created_at", -1)],
      )
      if latest:
        earlier = await pullups_collection.find(
          {"user_id": ObjectId(user_id), "created_at": {"$gte": latest["created_at"] - timedelta(hours=1)}},
          {"created_at": 1},
        ).sort("created_at", 1).to_list(length=None)
        last_times = [pullup["created_at"] for pullup in earlier]
    last_set = group_into_sets(last_times)[-1] if last_times else None

    today_sets = split_into_sets(today_times)
    week_sets = split_into_sets(week_times)
    days_elapsed = today.weekday() + 1

    return {
      "today": {
        "count": len(today_times),
        "sets": len(today_sets),
        "best_set": max(today_sets, default=0),
        "last_at": today_times[-1] if today_times else None,
      },
      "week": {
        "count": len(week_times),
        "daily_average": round(len(week_times) / days_elapsed, 1),
        "best_set": max(week_sets, default=0),
        "last_week_to_date": sum(1 for moment in last_week_times if moment <= same_point_last_week),
        "last_week_total": len(last_week_times),
      },
      "all_time": {
        "count": sum(daily.values()),
        "active_days": len(daily),
        "streak_days": get_streak_days(set(daily), today),
        "first_day": min(daily).isoformat() if daily else None,
        "best_day": {"date": best_day[0].isoformat(), "count": best_day[1]} if best_day else None,
      },
      "last_set": {"count": len(last_set), "at": last_set[-1]} if last_set else None,
      "set_gap_seconds": int(SET_GAP.total_seconds()),
    }


pullup_service = PullupService()
