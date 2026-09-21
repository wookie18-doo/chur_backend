from fastapi.routing import APIRouter

from app.api.v1 import monitoring, users

v1_router = APIRouter()
v1_router.include_router(monitoring.router)
v1_router.include_router(users.router)
