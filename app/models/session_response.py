from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

class CategorySummary(BaseModel):
    id: str
    label: str
    color: Optional[str] = None
    tag_colors: dict[str, str] = Field(default_factory=dict)

class SessionListItemResponse(BaseModel):
    id: str
    category_id: str
    category: Optional[CategorySummary] = None
    status: str
    is_active: bool
    start_time: datetime
    end_time: Optional[datetime] = None
    elapsed_time: Optional[int] = None
    tags: str = ""
    notes: str = ""
    distractions: int = 0
    note_count: int = 0
    latest_note: str = ""


class SessionListResponse(BaseModel):
    items: list[SessionListItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int