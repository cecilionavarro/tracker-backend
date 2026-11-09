from fastapi import APIRouter, HTTPException, Query, Request

from app.models.category_request import CategoryCreateRequest, CategoryUpdateRequest
from app.models.category_response import CategoryResponse
from app.services.category_service import CategoryError, category_service

router = APIRouter()


@router.get("/categories", response_model=list[CategoryResponse])
async def get_categories(request: Request, include_archived: bool = Query(False)):
    user_id = request.app.state.user_id
    return await category_service.list_categories(user_id, include_archived)


@router.post("/categories", response_model=CategoryResponse, status_code=201)
async def create_category(request: Request, data: CategoryCreateRequest):
    try:
        category = await category_service.create_category(request.app.state.user_id, data.model_dump())
    except CategoryError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
    request.app.state.state_manager.notify_dashboards()
    return category


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(request: Request, category_id: str, changes: CategoryUpdateRequest):
    try:
        category = await category_service.update_category(
            request.app.state.user_id, category_id, changes.model_dump(exclude_none=True)
        )
    except CategoryError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
    request.app.state.state_manager.notify_dashboards()
    return category


@router.delete("/categories/{category_id}")
async def delete_category(request: Request, category_id: str):
    try:
        deleted = await category_service.delete_category(request.app.state.user_id, category_id)
    except CategoryError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
    request.app.state.state_manager.notify_dashboards()
    return {"ok": True, "deleted_category_id": deleted["id"]}
