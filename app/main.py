import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.router import api_router
from app.hardware.gpio_handler import GPIOController
from app.services.state_manager import StateManager

@asynccontextmanager
async def lifespan(app: FastAPI):
  loop = asyncio.get_running_loop()
  app.state.state_manager = StateManager(loop)
  app.state.gpio = GPIOController(app.state.state_manager)
  try:
    yield
  finally:
    app.state.gpio.stop()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(api_router)

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)
