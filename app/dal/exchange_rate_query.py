"""Router in front of the concrete exchange-rate DAO."""

from datetime import date
from decimal import Decimal

from sqlmodel import col, select

from app.dal.sql.exchange_rate_dao import ExchangeRateDAO
from app.db.sql.models.currency import ExchangeRate


class ExchangeRateQuery(ExchangeRateDAO):
    """Everything ``ExchangeRateService`` needs to read and write rates."""

    async def latest(
        self, currency_code: str, base_currency: str
    ) -> ExchangeRate | None:
        """
        Fetch the most recent rate of a currency against a base.

        :param currency_code: currency to look up.
        :param base_currency: base the rate is quoted against.
        :return: the newest row, or ``None`` if none was ever fetched.
        """
        query = (
            select(ExchangeRate)
            .where(ExchangeRate.currency_code == currency_code)
            .where(ExchangeRate.base_currency == base_currency)
            .order_by(col(ExchangeRate.as_of).desc())
            .limit(1)
        )
        result = await self.session.exec(query)
        return result.first()

    async def upsert_for_day(
        self, currency_code: str, base_currency: str, rate: Decimal, as_of: date
    ) -> ExchangeRate:
        """
        Store a day's rate, updating in place if it already exists.

        Makes the daily job safely re-runnable.

        :param currency_code: currency being quoted.
        :param base_currency: base the rate is quoted against.
        :param rate: amount of ``currency_code`` per 1 unit of the base.
        :param as_of: the rate's own date.
        :return: the stored row.
        """
        query = (
            select(ExchangeRate)
            .where(ExchangeRate.currency_code == currency_code)
            .where(ExchangeRate.base_currency == base_currency)
            .where(ExchangeRate.as_of == as_of)
        )
        existing = (await self.session.exec(query)).first()
        if existing is None:
            return await self.create(
                currency_code=currency_code,
                base_currency=base_currency,
                rate=rate,
                as_of=as_of,
            )
        existing.rate = rate
        await self.session.flush()
        return existing
