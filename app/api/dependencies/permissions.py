from collections.abc import Callable, Coroutine
from typing import Any, cast

from fastapi import Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.db import get_db_session
from app.db.sql.models.users import User
from app.services.permission_service import PermissionService


def get_permission_service(
    user: RequestUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
) -> PermissionService:
    """
    Build a :class:`~app.services.permission_service.PermissionService`.

    :param user: the currently authenticated user.
    :param session: asynchronous database session.
    :return: service instance.
    """
    # require_auth already guarantees unwrap() isn't None here.
    resolved = cast(User, user.unwrap())
    return PermissionService(resolved, session)


def require_superuser(
    permission_service: PermissionService = Depends(get_permission_service),
) -> User:
    """
    FastAPI dependency that only lets superusers through.

    Use it exactly like ``require_auth``:
    ``Depends(require_superuser)``.

    :param permission_service: permission service for the current user.
    :return: the current user, once confirmed to be a superuser.
    :raises HTTPException: 403, if the user is not a superuser.
    """
    if not permission_service.is_superuser():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges.",
        )
    return permission_service.user


def require_permissions(
    permissions: list[str],
) -> Callable[..., Coroutine[Any, Any, User]]:
    """
    Build a FastAPI dependency requiring the given permissions.

    Only lets users with every permission in ``permissions`` through;
    superusers always pass. Use it like ``require_auth``, but call it
    with the permissions you want to require:
    ``Depends(require_permissions(["posts:write"]))``.

    :param permissions: permission names the user must hold.
    :return: dependency raising 403 if the user is missing any of them.
    """

    async def dependency(
        permission_service: PermissionService = Depends(get_permission_service),
    ) -> User:
        if not await permission_service.has_permissions(permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions.",
            )
        return permission_service.user

    return dependency
