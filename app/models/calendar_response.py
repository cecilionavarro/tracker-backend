from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.dashboard_activity_response import DashboardActivityCategoryResponse
from app.models.session_response import CategorySummary


class CalendarBlock(BaseModel):
    # The part of a session that falls on this day; sessions crossing midnight
    # appear on both days.
    session_id: str
    start: datetime
    # None while the session is still running.
    end: Optional[datetime] = None
    # Wall-clock minutes from the day's midnight, 0 to 1440.
    start_minute: float
    end_minute: float
    is_active: bool
    category: Optional[CategorySummary] = None
    tags: str = ""
    session_start: datetime
    session_end: Optional[datetime] = None
    session_seconds: int
    distractions: int = 0


class CalendarMarker(BaseModel):
    kind: Literal["distraction", "pullups", "note"]
    at: datetime
    minute: float
    # Reps, for a pull-up set.
    count: Optional[int] = None
    # The note's text.
    text: Optional[str] = None
    session_id: Optional[str] = None


class CalendarDay(BaseModel):
    date: str
    worked_seconds: int
    categories: list[DashboardActivityCategoryResponse] = Field(default_factory=list)
    blocks: list[CalendarBlock] = Field(default_factory=list)
    markers: list[CalendarMarker] = Field(default_factory=list)


class CalendarResponse(BaseModel):
    start: str
    days: int
    entries: list[CalendarDay]
