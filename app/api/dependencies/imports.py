"""Wiring for the imports subsystem."""

from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.import_service import ImportService
from app.services.imports.storage import ImportFileStore


def get_import_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ImportService:
    """
    Build an :class:`~app.services.import_service.ImportService`.

    :param request: current request, for the shared redis client.
    :param session: asynchronous database session.
    :return: service instance.
    """
    return ImportService(session, ImportFileStore(request.app.state.redis_client))
