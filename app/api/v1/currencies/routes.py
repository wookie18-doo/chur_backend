from fastapi import APIRouter, Depends

from app.api.dependencies.auth import require_auth
from app.api.dependencies.currencies import get_currency_service
from app.api.v1.currencies.schema import CurrencyRead
from app.db.sql.models.currency import Currency
from app.services.currency_service import CurrencyService

router = APIRouter(
    prefix="/currencies", tags=["currencies"], dependencies=[Depends(require_auth)]
)


@router.get("", response_model=list[CurrencyRead])
async def list_currencies(
    service: CurrencyService = Depends(get_currency_service),
) -> list[Currency]:
    """
    List the currencies currently offered for new accounts.

    :param service: currency service.
    :return: active currencies, ordered by code.
    """
    return await service.list_active()
