from fastapi import APIRouter, HTTPException, Query, Request

from app.models.note import NoteCreateRequest, NoteResponse, NoteUpdateRequest
from app.models.worklog_response import WorklogResponse
from app.services.note_service import NoteError, note_service
from app.services.worklog_service import worklog_service

router = APIRouter()


@router.get("/sessions/{session_id}/notes", response_model=list[NoteResponse])
async def get_session_notes(request: Request, session_id: str):
    try:
        return await note_service.list_session_notes(request.app.state.user_id, session_id)
    except NoteError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))


@router.post("/notes", response_model=NoteResponse, status_code=201)
async def create_note(request: Request, data: NoteCreateRequest):
    try:
        note = await note_service.create_note(request.app.state.user_id, data.model_dump())
    except NoteError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
    request.app.state.state_manager.notify_dashboards()
    return note


@router.patch("/notes/{note_id}", response_model=NoteResponse)
async def update_note(request: Request, note_id: str, changes: NoteUpdateRequest):
    try:
        note = await note_service.update_note(
            request.app.state.user_id, note_id, changes.model_dump(exclude_none=True)
        )
    except NoteError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
    request.app.state.state_manager.notify_dashboards()
    return note


@router.delete("/notes/{note_id}")
async def delete_note(request: Request, note_id: str):
    try:
        deleted = await note_service.delete_note(request.app.state.user_id, note_id)
    except NoteError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
    request.app.state.state_manager.notify_dashboards()
    return {"ok": True, "deleted_note_id": deleted["id"]}


@router.get("/worklog", response_model=WorklogResponse)
async def get_worklog(request: Request, days: int = Query(default=7, ge=1, le=90)):
    return await worklog_service.get_worklog(request.app.state.user_id, days)
