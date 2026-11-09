from fastapi import APIRouter, HTTPException, Request

from app.models.counter_response import DistractionCountResponse, PullupCountResponse, PullupStatsResponse
from app.hardware.gpio_handler import SAVED_FLASHES
from app.services.pullup_service import pullup_service

router = APIRouter()

# The Pi's counter buttons call the same state manager methods, so every
# open dashboard refreshes whichever way a count changes.


@router.get("/pullups/stats", response_model=PullupStatsResponse)
async def get_pullup_stats(request: Request):
    return await pullup_service.get_stats(request.app.state.user_id)


@router.post("/pullups", response_model=PullupCountResponse)
async def add_pullup(request: Request):
    today = await request.app.state.state_manager.record_pullup(source="api")
    return {"today": today}


@router.delete("/pullups/last", response_model=PullupCountResponse)
async def remove_last_pullup(request: Request):
    today = await request.app.state.state_manager.remove_pullup()

    if today is None:
        raise HTTPException(status_code=404, detail="No pull-ups to undo today.")

    return {"today": today}


@router.post("/sessions/active/distractions", response_model=DistractionCountResponse)
async def add_distraction(request: Request):
    result = await request.app.state.state_manager.record_distraction(source="api")

    if result is None:
        raise HTTPException(status_code=409, detail="Clock in to count distractions.")

    # The same double flash as the Pi's distraction button.
    request.app.state.gpio.flash_led(SAVED_FLASHES)
    return result


@router.delete("/sessions/active/distractions", response_model=DistractionCountResponse)
async def remove_distraction(request: Request):
    result = await request.app.state.state_manager.remove_distraction()

    if result is None:
        raise HTTPException(status_code=409, detail="No session is running.")

    return result
