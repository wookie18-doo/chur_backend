"""Scheduled refresh of currency exchange rates."""

from sqlmodel.ext.asyncio.session import AsyncSession
from taskiq import TaskiqDepends

from app.api.dependencies.db import get_db_session
from app.services.exchange_rate_service import ExchangeRateService
from app.tasks.broker import broker


@broker.task(schedule=[{"cron": "0 5 * * *"}])
async def refresh_exchange_rates(
    session: AsyncSession = TaskiqDepends(get_db_session),
) -> None:
    """Refresh currency exchange rates, once a day at 05:00."""
    await ExchangeRateService(session).refresh_rates()
