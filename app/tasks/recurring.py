"""Scheduled generation of occurrences for due recurring transactions."""

from sqlmodel.ext.asyncio.session import AsyncSession
from taskiq import TaskiqDepends

from app.api.dependencies.db import get_db_session
from app.services.recurring_transaction_service import RecurringTransactionService
from app.tasks.broker import broker


@broker.task(schedule=[{"cron": "0 6 * * *"}])
async def generate_due_recurring_occurrences(
    session: AsyncSession = TaskiqDepends(get_db_session),
) -> None:
    """Surface every recurring rule that's due, once a day at 06:00."""
    await RecurringTransactionService(session).generate_due_occurrences()
