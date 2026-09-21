from fastapi import HTTPException, status
from starlette.requests import Request

from app.api.base.base import RequestUser


async def require_auth(request: Request) -> RequestUser:
    """
    FastAPI dependency requiring a logged-in, active user.

    Reads the :class:`~app.api.base.base.RequestUser` that
    ``app.api.middlewares.auth.AuthMiddleware`` already attached to
    ``request.state.user`` for this request -- it doesn't resolve the token
    itself. Use it exactly like ``Depends(require_auth)`` wherever a route
    must reject anonymous or inactive requests; routes that only want to
    know who's asking (without rejecting anyone) can read
    ``request.state.user`` directly and check ``.is_authorized`` themselves.

    :param request: current request.
    :raises HTTPException: 401, if there's no authenticated user, or the
        account is inactive.
    :return: the authenticated, active user proxy.
    """
    user: RequestUser = request.state.user
    if not user.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
        )
    return user
