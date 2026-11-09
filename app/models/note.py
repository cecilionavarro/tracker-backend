from datetime import datetime
from typing import Optional

from pydantic import AwareDatetime, BaseModel, Field

MAX_NOTE_LENGTH = 2000


class NoteCreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_NOTE_LENGTH)
    # When it happened; defaults to now.
    at: Optional[AwareDatetime] = None
    # Attach to this session. Without it, the note joins whichever session was
    # running at its time, or stands alone.
    session_id: Optional[str] = None


# Omitted (or null) fields stay unchanged.
class NoteUpdateRequest(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=MAX_NOTE_LENGTH)
    at: Optional[AwareDatetime] = None


class NoteResponse(BaseModel):
    id: str
    session_id: Optional[str] = None
    text: str
    at: datetime
    created_at: datetime
    updated_at: datetime
