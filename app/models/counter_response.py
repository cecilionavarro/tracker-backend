from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PullupCountResponse(BaseModel):
  # Pull-ups so far today, in the dashboard's timezone.
  today: int


class DistractionCountResponse(BaseModel):
  session_id: str
  distractions: int


class PullupTodayStats(BaseModel):
  count: int
  sets: int
  best_set: int
  last_at: Optional[datetime] = None


class PullupWeekStats(BaseModel):
  count: int
  daily_average: float
  best_set: int
  # Last week up to the same weekday and time, to compare with this week so far.
  last_week_to_date: int
  last_week_total: int


class PullupBestDay(BaseModel):
  date: str
  count: int


class PullupAllTimeStats(BaseModel):
  count: int
  active_days: int
  streak_days: int
  best_day: Optional[PullupBestDay] = None
  # The first day with a pull-up, as YYYY-MM-DD in the overview's timezone.
  first_day: Optional[str] = None


class PullupLastSet(BaseModel):
  count: int
  # When its last rep was tapped.
  at: datetime


class PullupStatsResponse(BaseModel):
  today: PullupTodayStats
  week: PullupWeekStats
  all_time: PullupAllTimeStats
  last_set: Optional[PullupLastSet] = None
  # Presses closer together than this count as one set.
  set_gap_seconds: int
