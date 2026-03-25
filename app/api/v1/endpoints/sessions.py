from fastapi import APIRouter, Query, Request

from app.core.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.services.session_service import session_service
from app.models.session_response import SessionListResponse

router = APIRouter()


@router.get("/sessions", response_model=SessionListResponse)
async def get_sessions(
    request: Request,
    page: int = Query(DEFAULT_PAGE, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    user_id = request.app.state.user_id
    return await session_service.list_sessions(user_id, page, page_size)
