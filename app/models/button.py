from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.session_response import CategorySummary


# "activity" clocks into a category and tag; the counters add one per press.
ButtonAction = Literal["activity", "pullup", "distraction", "none"]


class ButtonResponse(BaseModel):
    pin: int
    physical_pin: Optional[int] = None
    action: ButtonAction = "none"
    # Set only for "activity".
    category: Optional[CategorySummary] = None
    tags: str = ""


class ButtonAssignRequest(BaseModel):
    # Without an action, a category means "activity" and None means "none".
    action: Optional[ButtonAction] = None
    category_id: Optional[str] = None
    tags: str = Field(default="", max_length=30)
