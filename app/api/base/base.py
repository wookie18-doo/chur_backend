"""
Shared building blocks for resolving "who is making this request".

:class:`RequestUser` is the value every request ends up with attached at
``request.state.user``; :class:`RequestUserAuth` is the reusable behavior
that produces one from a raw request (token extraction, decoding, db
lookup). ``app.api.middlewares.auth.AuthMiddleware`` mixes
:class:`RequestUserAuth` in so its ``dispatch`` can just call ``self.auth``
-- any other entrypoint that needs the same resolution (a future
non-middleware transport, tests, ...) can mix it in the same way instead of
duplicating the logic.
"""

from typing import Any

from starlette.requests import Request

from app.api.dependencies.users import get_email_sender
from app.config.settings import settings
from app.db.sql.models.users import User
from app.services.auth_service import InvalidTokenError, decode_token
from app.services.user_service import UserService


class RequestUser:
    """
    Stand-in for the user making the current request.

    Mirrors Django's ``request.user``/``AnonymousUser`` pattern: when the
    request carries a valid token this proxies attribute access straight
    through to the resolved db :class:`~app.db.sql.models.users.User`; when
    it doesn't, it behaves as an anonymous mock instead of ``None``, so
    callers can check ``.is_authorized`` (and ``.is_active``, always
    ``False`` for an anonymous request) without a null check first.
    """

    def __init__(self, user: User | None = None) -> None:
        self._user = user

    @property
    def is_authorized(self) -> bool:
        """Whether the request resolved to a real, known user."""
        return self._user is not None

    @property
    def is_active(self) -> bool:
        """Whether the underlying account is active (``False`` if anonymous)."""
        return self._user is not None and self._user.is_active

    def unwrap(self) -> User | None:
        """
        Return the underlying db user.

        :return: the real user, or ``None`` if this is an anonymous request.
        """
        return self._user

    def __getattr__(self, name: str) -> Any:
        if self._user is None:
            raise AttributeError(
                f"Anonymous user has no attribute {name!r} -- check "
                "is_authorized before reading anything but is_authorized/is_active."
            )
        return getattr(self._user, name)


class RequestUserAuth:
    """
    Mixin resolving a :class:`RequestUser` from a raw request.

    Holds no state of its own -- it's meant to be mixed into whatever needs
    this behavior (see ``app.api.middlewares.auth.AuthMiddleware``), not
    instantiated on its own.
    """

    def _extract_token(self, request: Request) -> str | None:
        """
        Pull the raw access token out of the request, if present.

        :param request: current request.
        :return: the token string, or ``None`` if neither the header nor
            the cookie carried one.
        """
        authorization = request.headers.get("Authorization")
        if authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() == "bearer" and token:
                return token
        session_token = request.cookies.get(settings.users_cookie_name)
        if session_token:
            return session_token
        return None

    async def _resolve_user(self, request: Request) -> RequestUser:
        """
        Decode the request's token (if any) and look up the user it names.

        :param request: current request.
        :return: proxy wrapping the resolved user, or an anonymous stand-in.
        """
        token = self._extract_token(request)
        if token is None:
            return RequestUser(None)

        try:
            user_id = decode_token(token, expected_type="access")
        except InvalidTokenError:
            return RequestUser(None)
        session_factory = request.app.state.db_session_factory
        async with session_factory() as session:
            user = await UserService(session, get_email_sender()).get_by_id(user_id)
        return RequestUser(user)

    async def auth(self, request: Request) -> RequestUser:
        """
        Resolve the current request's user.

        Public entry point for :meth:`_resolve_user` -- callers (e.g.
        :class:`~app.api.middlewares.auth.AuthMiddleware`) call this rather
        than the underscore-prefixed helpers.

        :param request: current request.
        :return: proxy wrapping the resolved user, or an anonymous stand-in.
        """
        return await self._resolve_user(request)
