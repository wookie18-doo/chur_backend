from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.currency_query import CurrencyQuery
from app.db.sql.models.currency import Currency


class CurrencyService:
    """Business logic around currency reference data."""

    def __init__(self, session: AsyncSession) -> None:
        self.dao = CurrencyQuery(session)

    async def list_active(self) -> list[Currency]:
        """
        List the currencies currently offered for new accounts.

        :return: active currencies, ordered by code.
        """
        return await self.dao.list_active()
