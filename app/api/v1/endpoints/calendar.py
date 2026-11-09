from datetime import date

from fastapi import APIRouter, Query, Request

from app.models.calendar_response import CalendarResponse
from app.services.calendar_service import calendar_service

router = APIRouter()


# Days are calendar days in the tracker's timezone, starting at `start`.
@router.get("/calendar", response_model=CalendarResponse)
async def get_calendar(request: Request, start: date, days: int = Query(default=7, ge=1, le=14)):
    return await calendar_service.get_calendar(request.app.state.user_id, start, days)
