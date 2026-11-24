from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.middlewares.auth import AuthMiddleware
from app.api.pages import router as pages_router
from app.api.router import api_router
from app.lifespan import lifespan_setup

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="chur",
    lifespan=lifespan_setup,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
# Resolves request.state.user for every request.
app.add_middleware(AuthMiddleware)

# Main router for the API.
app.include_router(router=api_router, prefix="/api")

# Public HTML pages served from the site root.
app.include_router(router=pages_router)

# Logo and favicon used by the public pages.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
