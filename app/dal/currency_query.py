"""Router in front of the concrete currency DAO."""

from sqlmodel import col, select

from app.dal.sql.currency_dao import CurrencyDAO
from app.db.sql.models.currency import Currency


class CurrencyQuery(CurrencyDAO):
    """Everything the services need to read currency reference data."""

    async def list_active(self) -> list[Currency]:
        """
        Fetch the currencies currently offered for new accounts.

        :return: active currencies, ordered by code.
        """
        query = (
            select(Currency)
            .where(col(Currency.is_active).is_(True))
            .order_by(col(Currency.code))
        )
        result = await self.session.exec(query)
        return list(result.all())
