from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class CategoryModel(BaseModel):
  id: Optional[str] = Field(alias="_id", default=None)
  group_id: Optional[str] = None
  key: str
  label: str
  active: bool = True
  color: str = None
  created_at: datetime
  updated_at: datetime