from fastapi import APIRouter, HTTPException, Query, Request

from app.core.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.services.session_service import SessionUpdateError, session_service
from app.models.session_response import SessionListItemResponse, SessionListResponse
from app.models.session_update_request import SessionUpdateRequest

router = APIRouter()

@router.get("/sessions", response_model=SessionListResponse)
async def get_sessions(
    request: Request,
    page: int = Query(DEFAULT_PAGE, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    user_id = request.app.state.user_id
    return await session_service.list_sessions(user_id, page, page_size)


@router.patch("/sessions/{session_id}", response_model=SessionListItemResponse)
async def update_session(request: Request, session_id: str, changes: SessionUpdateRequest):
    user_id = request.app.state.user_id

    try:
      session = await session_service.update_session(
        user_id, session_id, changes.model_dump(exclude_none=True)
      )
    except SessionUpdateError as error:
      raise HTTPException(status_code=error.status_code, detail=str(error))

    if not session:
      raise HTTPException(status_code=404, detail="Session not found")

    # The edit may have changed or stopped the running session. Reload it so
    # the next button press and the LED match, and refresh open dashboards.
    await request.app.state.state_manager.sync_active_session()
    request.app.state.gpio.sync_led()

    return session


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
