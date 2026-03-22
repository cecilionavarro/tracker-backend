from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class Session(BaseModel):
  # view in detail later id
  id: Optional[str] = Field(alias="_id", default=None)
  user_id: str
  status: str
  start_time: datetime
  end_time: Optional[datetime] = None
  elapsed_time: Optional[int] = None
  notes: str