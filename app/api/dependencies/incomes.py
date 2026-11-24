"""Wiring for the incomes subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.income_service import IncomeService


def get_income_service(
    session: AsyncSession = Depends(get_db_session),
) -> IncomeService:
    """
    Build a :class:`~app.services.income_service.IncomeService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return IncomeService(session)
