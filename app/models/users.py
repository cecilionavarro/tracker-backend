from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class Users(BaseModel):
  id: Optional[str] = Field(alias="_id", default=None)
  username: str
  email: str
  role: str
  created_at: datetime