"""Wiring for the statement-sources subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.statement_source_service import StatementSourceService


def get_statement_source_service(
    session: AsyncSession = Depends(get_db_session),
) -> StatementSourceService:
    """
    Build a :class:`~app.services.statement_source_service.StatementSourceService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return StatementSourceService(session)
