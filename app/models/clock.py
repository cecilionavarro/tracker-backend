from typing import Optional

from pydantic import BaseModel, Field


class ClockInRequest(BaseModel):
    category_id: str
    tags: str = Field(default="", max_length=30)


class ClockStateResponse(BaseModel):
    clocked_in: bool
    started_at: Optional[str] = None
    category_id: Optional[str] = None
    tags: str = ""
