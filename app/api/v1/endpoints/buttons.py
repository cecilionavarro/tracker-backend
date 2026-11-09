from fastapi import APIRouter, HTTPException, Request

from app.models.button import ButtonAssignRequest, ButtonResponse
from app.services.button_service import ButtonError, button_service

router = APIRouter()


@router.get("/buttons", response_model=list[ButtonResponse])
async def get_buttons():
    return await button_service.list_buttons()


# Takes effect on the button's next press; no restart needed.
@router.patch("/buttons/{pin}", response_model=ButtonResponse)
async def assign_button(request: Request, pin: int, data: ButtonAssignRequest):
    try:
        button = await button_service.assign(pin, data.category_id, data.tags, data.action)
    except ButtonError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
    request.app.state.state_manager.notify_dashboards()
    return button
