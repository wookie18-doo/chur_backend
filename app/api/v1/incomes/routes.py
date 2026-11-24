import uuid
from datetime import date
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.incomes import get_income_service
from app.api.v1.incomes.schema import IncomeCreate, IncomeRead, IncomeUpdate
from app.db.sql.models.income import Income
from app.db.sql.models.users import User
from app.services.income_service import (
    IncomeNotFoundError,
    IncomeService,
    InvalidAccountError,
)

router = APIRouter(prefix="/incomes", tags=["incomes"])


@router.get("", response_model=list[IncomeRead])
async def list_incomes(
    *,
    scope: str = Query("me", pattern="^(me|family)$"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    category_id: int | None = Query(None),
    account_id: uuid.UUID | None = Query(None),
    user: RequestUser = Depends(require_auth),
    income_service: IncomeService = Depends(get_income_service),
) -> list[Income]:
    """
    List incomes visible to the current user.

    :param scope: ``"me"`` or ``"family"``.
    :param date_from: earliest date to include, inclusive.
    :param date_to: latest date to include, inclusive.
    :param category_id: restrict to one category.
    :param account_id: restrict to one account.
    :param user: the authenticated user.
    :param income_service: income service.
    :return: matching incomes.
    """
    return await income_service.list_incomes(
        cast(User, user.unwrap()),
        scope=scope,
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        account_id=account_id,
    )


@router.post("", response_model=IncomeRead, status_code=status.HTTP_201_CREATED)
async def create_income(
    payload: IncomeCreate,
    user: RequestUser = Depends(require_auth),
    income_service: IncomeService = Depends(get_income_service),
) -> Income:
    """
    Log a new income for the current user.

    :param payload: income-creation payload.
    :param user: the authenticated user.
    :param income_service: income service.
    :raises HTTPException: 400, if ``account_id`` isn't the user's.
    :return: the created income.
    """
    try:
        return await income_service.create(
            cast(User, user.unwrap()),
            account_id=payload.account_id,
            category_id=payload.category_id,
            amount=payload.amount,
            received_at=payload.received_at,
            description=payload.description,
            visibility=payload.visibility,
        )
    except InvalidAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id must name one of your own accounts.",
        ) from exc


@router.get("/{income_id}", response_model=IncomeRead)
async def read_income(
    income_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    income_service: IncomeService = Depends(get_income_service),
) -> Income:
    """
    Fetch an income the current user is allowed to read.

    :param income_id: income to fetch.
    :param user: the authenticated user.
    :param income_service: income service.
    :raises HTTPException: 404, if it doesn't exist or isn't visible.
    :return: the income.
    """
    try:
        return await income_service.get_visible(cast(User, user.unwrap()), income_id)
    except IncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Income not found."
        ) from exc


@router.patch("/{income_id}", response_model=IncomeRead)
async def update_income(
    income_id: uuid.UUID,
    payload: IncomeUpdate,
    user: RequestUser = Depends(require_auth),
    income_service: IncomeService = Depends(get_income_service),
) -> Income:
    """
    Update fields on an income owned by the current user.

    :param income_id: income to update.
    :param payload: fields to change; omitted fields are left as-is.
    :param user: the authenticated user.
    :param income_service: income service.
    :raises HTTPException: 404/400, see the service's own errors.
    :return: the updated income.
    """
    try:
        return await income_service.update(
            cast(User, user.unwrap()),
            income_id,
            **payload.model_dump(exclude_unset=True),
        )
    except IncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Income not found."
        ) from exc
    except InvalidAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id must name one of your own accounts.",
        ) from exc


@router.delete("/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_income(
    income_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    income_service: IncomeService = Depends(get_income_service),
) -> None:
    """
    Delete an income owned by the current user.

    :param income_id: income to delete.
    :param user: the authenticated user.
    :param income_service: income service.
    :raises HTTPException: 404, if it isn't owned by the user.
    """
    try:
        await income_service.delete(cast(User, user.unwrap()), income_id)
    except IncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Income not found."
        ) from exc
