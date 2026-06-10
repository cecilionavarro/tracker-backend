from pydantic import BaseModel


class DashboardActivityPointResponse(BaseModel):
    date: str
    time_worked: int
    session_count: int


class DashboardActivityResponse(BaseModel):
    days: int
    points: list[DashboardActivityPointResponse]