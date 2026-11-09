from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.note import NoteResponse
from app.models.session_response import CategorySummary


class WorklogSession(BaseModel):
    id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    is_active: bool
    seconds: int
    category: Optional[CategorySummary] = None
    tags: str = ""
    distractions: int = 0
    notes: list[NoteResponse] = Field(default_factory=list)


class WorklogDay(BaseModel):
    date: str
    # Time worked that day, splitting sessions at midnight like the overview.
    worked_seconds: int
    session_count: int
    pullups: int = 0
    sessions: list[WorklogSession] = Field(default_factory=list)
    # Notes that aren't part of a listed session.
    notes: list[NoteResponse] = Field(default_factory=list)


class WorklogResponse(BaseModel):
    days: int
    # Days with sessions or notes, newest first.
    entries: list[WorklogDay]
