"""Wiring for the spents subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.spent_service import SpentService


def get_spent_service(
    session: AsyncSession = Depends(get_db_session),
) -> SpentService:
    """
    Build a :class:`~app.services.spent_service.SpentService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return SpentService(session)
