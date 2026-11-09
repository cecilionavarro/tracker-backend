from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.dashboard_activity_response import DashboardActivityCategoryResponse
from app.models.session_response import CategorySummary


class OverviewActiveSessionResponse(BaseModel):
    id: str
    start_time: datetime
    category: Optional[CategorySummary] = None
    tags: str = ""
    distractions: int = 0


class OverviewDayResponse(BaseModel):
    status: str
    longest_session_seconds: int
    session_count: int
    first_session_at: Optional[datetime] = None
    goal_seconds: int
    worked_seconds: int
    active_session: Optional[OverviewActiveSessionResponse] = None
    pullups: int = 0
    # Distractions in sessions started today.
    distractions: int = 0


class OverviewWeekGraphDayResponse(BaseModel):
    day: str
    seconds: int
    goal_met: bool
    is_future: bool
    categories: list[DashboardActivityCategoryResponse] = Field(default_factory=list)
    pullups: int = 0
    distractions: int = 0


class OverviewWeekResponse(BaseModel):
    total_time_seconds: int
    longest_session_seconds: int
    session_count: int
    daily_average_seconds: int
    goal_completed_days: int
    graph: list[OverviewWeekGraphDayResponse]
    pullups: int = 0
    distractions: int = 0


class OverviewResponse(BaseModel):
    day: OverviewDayResponse
    week: OverviewWeekResponse