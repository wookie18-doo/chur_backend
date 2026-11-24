"""Wiring for the categories subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.category_service import CategoryService


def get_category_service(
    session: AsyncSession = Depends(get_db_session),
) -> CategoryService:
    """
    Build a :class:`~app.services.category_service.CategoryService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return CategoryService(session)
