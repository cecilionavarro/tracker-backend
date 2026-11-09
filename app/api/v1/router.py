from fastapi import APIRouter
from app.api.v1.endpoints import buttons, calendar, categories, clock, counters, dashboard, health, notes, overview, sessions
from app.api.v1.websockets import dashboard as dashboard_ws

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(categories.router, tags=["categories"])
api_router.include_router(counters.router, tags=["counters"])
api_router.include_router(clock.router, tags=["clock"])
api_router.include_router(notes.router, tags=["notes"])
api_router.include_router(buttons.router, tags=["buttons"])
api_router.include_router(calendar.router, tags=["calendar"])
api_router.include_router(overview.router, tags=["overview"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(dashboard_ws.router, tags=["dashboard"])