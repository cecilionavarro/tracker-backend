from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserModel(BaseModel):
    username: str
    email: EmailStr
    role: str
    created_at: datetime
