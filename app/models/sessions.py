from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class SessionModel(BaseModel):
  # view in detail later id
  id: Optional[str] = Field(alias="_id", default=None)
  user_id: str
  category_id: str
  status: str
  start_time: datetime
  end_time: Optional[datetime] = None
  elapsed_time: Optional[int] = None
  tags: str = ""
  notes: str = ""
  created_at: datetime
  updated_at: datetime
