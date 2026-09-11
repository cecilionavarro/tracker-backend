from pydantic import BaseModel, Field


class DashboardActivityCategoryResponse(BaseModel):
    id: str
    label: str
    color: str | None = None
    seconds: int
    tags: str = ""
    is_active: bool = False


class DashboardActivityPointResponse(BaseModel):
    date: str
    time_worked: int
    session_count: int
    categories: list[DashboardActivityCategoryResponse] = Field(default_factory=list)
    pianiso_technical: int
    pianiso_non_technical: int
    creating: int
    toycon: int


class DashboardActivityResponse(BaseModel):
    days: int
    points: list[DashboardActivityPointResponse]
