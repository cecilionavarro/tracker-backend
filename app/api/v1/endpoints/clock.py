from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from app.core.database import categories_collection
from app.models.clock import ClockInRequest, ClockStateResponse

router = APIRouter()

# Clocking in and out from the dashboard. Both go through the same state
# manager as the Pi's buttons, so the LED and every open dashboard follow.


@router.post("/clock/in", response_model=ClockStateResponse)
async def clock_in(request: Request, data: ClockInRequest):
    category = (
        await categories_collection.find_one({"_id": ObjectId(data.category_id)})
        if ObjectId.is_valid(data.category_id) else None
    )
    if not category:
        raise HTTPException(status_code=422, detail="Unknown category.")
    if category.get("active") is False:
        raise HTTPException(status_code=422, detail=f"{category['label']} is archived. Restore it first.")

    state_manager = request.app.state.state_manager
    await state_manager.clock_into(data.category_id, data.tags)
    request.app.state.gpio.sync_led()
    return state_manager.get_state()


@router.post("/clock/out", response_model=ClockStateResponse)
async def clock_out(request: Request):
    state_manager = request.app.state.state_manager
    if not await state_manager.clock_out_if_running():
        raise HTTPException(status_code=409, detail="You're not clocked in.")
    request.app.state.gpio.sync_led()
    return state_manager.get_state()
