from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config.settings import settings
from app.services.exchange_rate_service import (
    ExchangeRateFetchError,
    ExchangeRateService,
    NoExchangeRateAvailableError,
)

_REAL_CLIENT = httpx.AsyncClient


def _mock_provider(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _REAL_CLIENT(transport=httpx.MockTransport(handler), **kw),
    )
    return seen


async def test_refresh_rates_stores_and_upserts(
    dbsession: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful payload stores a row per active currency, once per day."""
    seen = _mock_provider(
        monkeypatch,
        {"success": True, "quotes": {"USDEUR": 0.9, "USDGBP": 0.75, "USDCHF": 0.88}},
    )
    service = ExchangeRateService(dbsession)
    today = date(2026, 10, 11)

    await service.refresh_rates(today=today)
    _mock_provider(monkeypatch, {"success": True, "quotes": {"USDEUR": 0.95}})
    await service.refresh_rates(today=today)

    assert "USD" not in seen[0].url.params["currencies"]
    assert await service.latest_rate("EUR") == Decimal("0.95")
    assert await service.latest_rate("GBP") == Decimal("0.75")
    assert len(await service.rates.retrieve(currency_code="EUR")) == 1


async def test_refresh_rates_raises_on_provider_error(
    dbsession: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A {success: false} payload surfaces instead of being swallowed."""
    _mock_provider(
        monkeypatch,
        {"success": False, "error": {"code": 101, "info": "invalid access key"}},
    )

    with pytest.raises(ExchangeRateFetchError, match="invalid access key"):
        await ExchangeRateService(dbsession).refresh_rates()


async def test_latest_rate_for_base_is_one_without_db(
    dbsession: AsyncSession,
) -> None:
    """The base currency is definitionally 1; unknown currencies raise."""
    service = ExchangeRateService(dbsession)

    assert await service.latest_rate(settings.exchange_rate_base_currency) == 1
    with pytest.raises(NoExchangeRateAvailableError):
        await service.latest_rate("CHF")
