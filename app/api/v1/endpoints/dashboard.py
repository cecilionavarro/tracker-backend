from fastapi import APIRouter, Query, Request

from app.models.dashboard_activity_response import DashboardActivityResponse
from app.models.overview_response import OverviewResponse
from app.services.dashboard_activity_service import dashboard_activity_service
from app.services.overview_service import overview_service

router = APIRouter(prefix="/dashboard")


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(request: Request):
    user_id = request.app.state.user_id
    return await overview_service.get_overview(user_id)


@router.get("/activity", response_model=DashboardActivityResponse)
async def get_activity(
    request: Request,
    days: int = Query(default=30, ge=1, le=90),
):
    user_id = request.app.state.user_id
    return await dashboard_activity_service.get_activity(user_id, days)