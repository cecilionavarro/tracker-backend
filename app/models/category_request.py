from typing import Optional

from pydantic import BaseModel, Field

HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class CategoryCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    color: Optional[str] = Field(default=None, pattern=HEX_COLOR)
    tags: list[str] = Field(default_factory=list, max_length=20)
    # Optional colors for individual tags, keyed by tag.
    tag_colors: dict[str, str] = Field(default_factory=dict)


# Omitted (or null) fields stay unchanged.
class CategoryUpdateRequest(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=40)
    color: Optional[str] = Field(default=None, pattern=HEX_COLOR)
    tags: Optional[list[str]] = Field(default=None, max_length=20)
    tag_colors: Optional[dict[str, str]] = None
    # False archives the category: hidden from pickers, history kept.
    active: Optional[bool] = None
