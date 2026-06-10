from fastapi import APIRouter
from app.api.v1.endpoints import dashboard, health, overview, sessions
from app.api.v1.websockets import dashboard as dashboard_ws

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(overview.router, tags=["overview"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(dashboard_ws.router, tags=["dashboard"])