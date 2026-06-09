from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class OverviewActiveSessionResponse(BaseModel):
    id: str
    start_time: datetime


class OverviewDayResponse(BaseModel):
    status: str
    longest_session_seconds: int
    session_count: int
    first_session_at: Optional[datetime] = None
    goal_seconds: int
    worked_seconds: int
    active_session: Optional[OverviewActiveSessionResponse] = None


class OverviewWeekGraphDayResponse(BaseModel):
    day: str
    seconds: int
    goal_met: bool
    is_future: bool


class OverviewWeekResponse(BaseModel):
    total_time_seconds: int
    longest_session_seconds: int
    session_count: int
    daily_average_seconds: int
    goal_completed_days: int
    graph: list[OverviewWeekGraphDayResponse]


class OverviewResponse(BaseModel):
    day: OverviewDayResponse
    week: OverviewWeekResponse