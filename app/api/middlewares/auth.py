"""
Auth middleware: resolves who's making the request before routing runs.

Runs on every request (REST and GraphQL alike, since it's registered on the
ASGI app itself, not on a specific router) and attaches a
:class:`~app.api.base.base.RequestUser` to ``request.state.user`` -- a real
token resolves to a proxy wrapping the db user, a missing/invalid one
resolves to an anonymous stand-in. Route dependencies never resolve the
token themselves; they just read ``request.state.user`` (see
``app.api.dependencies.auth.require_auth``).
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.base.base import RequestUserAuth


class AuthMiddleware(BaseHTTPMiddleware, RequestUserAuth):
    """
    Attaches :class:`~app.api.base.base.RequestUser` to ``request.state.user``.

    The actual token-extraction/db-lookup behavior lives on
    :class:`~app.api.base.base.RequestUserAuth`, mixed in here -- this class
    only wires that behavior into the ASGI middleware chain.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Resolve the request's user before handing off to the next handler.

        :param request: current request.
        :param call_next: the next handler in the middleware chain.
        :return: the downstream response.
        """
        request.state.user = await self.auth(request)
        return await call_next(request)
