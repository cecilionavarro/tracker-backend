from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class EventModel(BaseModel):
  # MongoDB uses '_id' as the primary key. 
  # We use Field(alias="_id") so Pydantic knows to map this 
  # to the database field while still letting you use 'id' in your Python code.
  
  id: Optional[str] = Field(alias="_id", default=None)
  session_id: str
  event_type: str
  source: str
  created_at: datetime
