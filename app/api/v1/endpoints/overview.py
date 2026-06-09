from fastapi import APIRouter, Request

from app.models.overview_response import OverviewResponse
from app.services.overview_service import overview_service

router = APIRouter()


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(request: Request):
    user_id = request.app.state.user_id
    return await overview_service.get_overview(user_id)