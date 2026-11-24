"""Wiring for the currencies subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.currency_service import CurrencyService


def get_currency_service(
    session: AsyncSession = Depends(get_db_session),
) -> CurrencyService:
    """
    Build a :class:`~app.services.currency_service.CurrencyService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return CurrencyService(session)
