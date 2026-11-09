from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PullupModel(BaseModel):
  # One document per pull-up button press.
  id: Optional[str] = Field(alias="_id", default=None)
  user_id: str
  source: str
  created_at: datetime
