from fastapi import APIRouter, HTTPException, Query, Request

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


@router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: str):
    user_id = request.app.state.user_id
    deleted = await session_service.delete_session(user_id, session_id)

    if not deleted:
      raise HTTPException(status_code=404, detail="Session not found")

    if deleted["was_active"]:
      await request.app.state.state_manager.clear_active_session()
      request.app.state.gpio.sync_led()

    return {
      "ok": True,
      "deleted_session_id": deleted["id"],
    }
