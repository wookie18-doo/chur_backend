from fastapi import FastAPI

from app.api.middlewares.auth import AuthMiddleware
from app.api.router import api_router
from app.lifespan import lifespan_setup

app = FastAPI(
    title="finance_manager",
    lifespan=lifespan_setup,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
# Resolves request.state.user for every request.
app.add_middleware(AuthMiddleware)

# Main router for the API.
app.include_router(router=api_router, prefix="/api")
