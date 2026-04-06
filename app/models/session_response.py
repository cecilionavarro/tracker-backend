from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SessionListItemResponse(BaseModel):
    id: str
    category_id: str
    status: str
    is_active: bool
    start_time: datetime
    end_time: Optional[datetime] = None
    elapsed_time: Optional[int] = None
    tags: str = ""
    notes: str = ""


class SessionListResponse(BaseModel):
    items: list[SessionListItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int