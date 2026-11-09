from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CategoryButton(BaseModel):
    # A Pi button that clocks into this category.
    pin: int
    label: str
    tags: str = ""


class CategoryResponse(BaseModel):
    id: str
    label: str
    color: Optional[str] = None
    tag_colors: dict[str, str] = Field(default_factory=dict)
    # Tags to offer in pickers: the category's own tags plus any already used
    # on its sessions. "" means no tag.
    tags: list[str] = Field(default_factory=list)
    # The tags set on the category itself.
    defined_tags: list[str] = Field(default_factory=list)
    # Tags already on its sessions.
    used_tags: list[str] = Field(default_factory=list)
    active: bool = True
    session_count: int = 0
    total_seconds: int = 0
    last_used_at: Optional[datetime] = None
    buttons: list[CategoryButton] = Field(default_factory=list)
