from typing import Optional

from pydantic import AwareDatetime, BaseModel, Field


# Omitted (or null) fields stay unchanged. Setting end_time on a running
# session clocks it out at that time.
class SessionUpdateRequest(BaseModel):
    start_time: Optional[AwareDatetime] = None
    end_time: Optional[AwareDatetime] = None
    category_id: Optional[str] = None
    tags: Optional[str] = Field(default=None, max_length=100)
    # Corrects the distraction count, e.g. after an accidental press.
    distractions: Optional[int] = Field(default=None, ge=0, le=1000)
