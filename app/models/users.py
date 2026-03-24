from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserModel(BaseModel):
  id: Optional[str] = Field(alias="_id", default=None)
  username: str
  email: EmailStr
  role: str
  created_at: datetime
  updated_at: datetime
