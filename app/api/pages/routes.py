from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.config.settings import settings

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

# Pages are static, so they are read once at import time.
_INDEX = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
_PRIVACY_POLICY = (STATIC_DIR / "privacy_policy.html").read_text(
    encoding="utf-8",
)
_SUPPORT = (STATIC_DIR / "support.html").read_text(encoding="utf-8")

_DELETE_ACCOUNT = (STATIC_DIR / "delete_account.html").read_text(
    encoding="utf-8",
)

router = APIRouter(include_in_schema=False)


def _render_index() -> str:
    html = _INDEX
    for key, url in (
        ("APP_STORE", settings.app_store_url),
        ("GOOGLE_PLAY", settings.google_play_url),
    ):
        html = html.replace(f"{{{{{key}_URL}}}}", url)
        html = html.replace(
            f"{{{{{key}_DISPLAY}}}}",
            "" if url else "display:none",
        )
    return html


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Landing page; store buttons are hidden when no URL is configured."""
    return HTMLResponse(_render_index())


@router.get("/privacy_policy", response_class=HTMLResponse)
async def privacy_policy() -> HTMLResponse:
    """Privacy policy page (static HTML)."""
    return HTMLResponse(_PRIVACY_POLICY)


@router.get("/support", response_class=HTMLResponse)
async def support() -> HTMLResponse:
    """Support contact page."""
    return HTMLResponse(_SUPPORT)


@router.get("/delete-account", response_class=HTMLResponse)
async def delete_account() -> HTMLResponse:
    """Web account deletion page: log in, confirm, then delete."""
    return HTMLResponse(_DELETE_ACCOUNT)
