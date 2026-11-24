"""Wiring for the planned-incomes subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.planned_income_service import PlannedIncomeService


def get_planned_income_service(
    session: AsyncSession = Depends(get_db_session),
) -> PlannedIncomeService:
    """
    Build a :class:`~app.services.planned_income_service.PlannedIncomeService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return PlannedIncomeService(session)
