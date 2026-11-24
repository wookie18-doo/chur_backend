"""Wiring for the families subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.family_service import FamilyService


def get_family_service(
    session: AsyncSession = Depends(get_db_session),
) -> FamilyService:
    """
    Build a :class:`~app.services.family_service.FamilyService` for the request.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return FamilyService(session)
