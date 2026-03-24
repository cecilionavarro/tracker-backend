from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class CategoryGroupModel(BaseModel):
  id: Optional[str] = Field(alias="_id", default=None)
  key: str
  label: str
  active: bool = True
  color: str
  created_at: datetime
  updated_at: datetime