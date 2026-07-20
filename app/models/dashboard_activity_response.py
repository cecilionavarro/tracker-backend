from pydantic import BaseModel


class DashboardActivityPointResponse(BaseModel):
    date: str
    time_worked: int
    session_count: int
    pianiso_technical: int
    pianiso_non_technical: int
    creating: int
    toycon: int


class DashboardActivityResponse(BaseModel):
    days: int
    points: list[DashboardActivityPointResponse]
