from fastapi import APIRouter
from app.api.v1.endpoints import health, sessions
from app.api.v1.websockets import dashboard

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(dashboard.router, tags=["dashboard"])