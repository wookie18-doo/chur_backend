"""Wiring for the recurring-transactions subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.recurring_transaction_service import RecurringTransactionService


def get_recurring_transaction_service(
    session: AsyncSession = Depends(get_db_session),
) -> RecurringTransactionService:
    """Build a recurring transaction service.

    :class:`~app.services.recurring_transaction_service.
    RecurringTransactionService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return RecurringTransactionService(session)
