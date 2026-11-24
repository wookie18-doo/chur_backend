from datetime import date
from decimal import Decimal

import httpx
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config.settings import settings
from app.dal.currency_query import CurrencyQuery
from app.dal.exchange_rate_query import ExchangeRateQuery


class ExchangeRateFetchError(Exception):
    """Raised when the exchange-rate provider reports a failure."""


class NoExchangeRateAvailableError(Exception):
    """Raised when a currency has no stored rate yet."""


class ExchangeRateService:
    """
    Keeps daily exchange rates for the active currencies up to date.

    Rates are made *available* here; reports don't convert with them yet.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.currencies = CurrencyQuery(session)
        self.rates = ExchangeRateQuery(session)

    async def refresh_rates(self, *, today: date | None = None) -> None:
        """
        Fetch today's rates for every active currency and store them.

        :param today: the rates' ``as_of`` date; defaults to today.
        :raises ExchangeRateFetchError: if the provider reports a failure,
            so a whole day's failed refresh surfaces instead of vanishing.
        """
        today = today or date.today()
        base = settings.exchange_rate_base_currency
        codes = [
            currency.code
            for currency in await self.currencies.list_active()
            if currency.code != base
        ]
        if not codes:
            return
        async with httpx.AsyncClient(timeout=15.0) as http:
            response = await http.get(
                settings.exchange_rate_api_url,
                params={
                    "access_key": settings.exchange_rate_api_key,
                    "source": base,
                    "currencies": ",".join(codes),
                },
            )
        payload = response.json()
        if not payload.get("success"):
            error = payload.get("error") or {}
            raise ExchangeRateFetchError(
                error.get("info") or error.get("type") or "Unknown provider error."
            )
        quotes: dict[str, float | str] = payload.get("quotes", {})
        for code in codes:
            quote = quotes.get(f"{base}{code}")
            if quote is None:
                continue
            await self.rates.upsert_for_day(code, base, Decimal(str(quote)), today)

    async def latest_rate(self, currency_code: str) -> Decimal:
        """
        Return the latest stored rate of a currency against the base.

        :param currency_code: currency to look up.
        :raises NoExchangeRateAvailableError: if nothing was ever fetched.
        :return: ``1`` for the base currency itself, else the newest rate.
        """
        base = settings.exchange_rate_base_currency
        if currency_code == base:
            return Decimal(1)
        row = await self.rates.latest(currency_code, base)
        if row is None:
            raise NoExchangeRateAvailableError
        return row.rate
