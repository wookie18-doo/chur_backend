import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.planned_incomes import get_planned_income_service
from app.api.v1.planned_incomes.schema import (
    PlannedIncomeCandidateRead,
    PlannedIncomeCreate,
    PlannedIncomeRead,
    PlannedIncomeRealise,
    PlannedIncomeUpdate,
)
from app.db.sql.models.income import Income
from app.db.sql.models.planned_income import PlannedIncome
from app.db.sql.models.users import User
from app.services.plan_repeat import InvalidRepeatError, repeat_fields
from app.services.planned_income_service import (
    InvalidAccountError,
    InvalidIncomeError,
    MissingAccountError,
    PlannedIncomeNotFoundError,
    PlannedIncomeService,
)

router = APIRouter(prefix="/planned-incomes", tags=["planned-incomes"])


@router.get("", response_model=list[PlannedIncomeRead])
async def list_planned_incomes(
    scope: str = Query("me", pattern="^(me|family)$"),
    user: RequestUser = Depends(require_auth),
    planned_income_service: PlannedIncomeService = Depends(get_planned_income_service),
) -> list[PlannedIncome]:
    """
    List planned incomes visible to the current user.

    :param scope: ``"me"`` or ``"family"``.
    :param user: the authenticated user.
    :param planned_income_service: planned income service.
    :return: matching planned incomes.
    """
    return await planned_income_service.list_planned_incomes(
        cast(User, user.unwrap()), scope=scope
    )


@router.post("", response_model=PlannedIncomeRead, status_code=status.HTTP_201_CREATED)
async def create_planned_income(
    payload: PlannedIncomeCreate,
    user: RequestUser = Depends(require_auth),
    planned_income_service: PlannedIncomeService = Depends(get_planned_income_service),
) -> PlannedIncome:
    """
    Create a planned income owned by the current user.

    :param payload: planned-income creation payload.
    :param user: the authenticated user.
    :param planned_income_service: planned income service.
    :raises HTTPException: 400, if ``account_id`` isn't the user's.
    :return: the created planned income.
    """
    try:
        return await planned_income_service.create(
            cast(User, user.unwrap()),
            payload.name,
            payload.category_id,
            payload.amount,
            date_from=payload.date_from,
            date_to=payload.date_to,
            frequency=payload.frequency,
            repeat_until=payload.repeat_until,
            visibility=payload.visibility,
            account_id=payload.account_id,
        )
    except InvalidAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id must name one of your own accounts.",
        ) from exc
    except InvalidRepeatError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="repeat needs a weekly, monthly or yearly frequency and a date.",
        ) from exc


@router.get("/{planned_income_id}", response_model=PlannedIncomeRead)
async def read_planned_income(
    planned_income_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    planned_income_service: PlannedIncomeService = Depends(get_planned_income_service),
) -> PlannedIncome:
    """
    Fetch a planned income the current user is allowed to read.

    :param planned_income_id: planned income to fetch.
    :param user: the authenticated user.
    :param planned_income_service: planned income service.
    :raises HTTPException: 404, if it doesn't exist or isn't visible.
    :return: the planned income.
    """
    try:
        return await planned_income_service.get_visible(
            cast(User, user.unwrap()), planned_income_id
        )
    except PlannedIncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Planned income not found."
        ) from exc


@router.patch("/{planned_income_id}", response_model=PlannedIncomeRead)
async def update_planned_income(
    planned_income_id: uuid.UUID,
    payload: PlannedIncomeUpdate,
    user: RequestUser = Depends(require_auth),
    planned_income_service: PlannedIncomeService = Depends(get_planned_income_service),
) -> PlannedIncome:
    """
    Update fields on a planned income owned by the current user.

    :param planned_income_id: planned income to update.
    :param payload: fields to change; omitted fields are left as-is.
    :param user: the authenticated user.
    :param planned_income_service: planned income service.
    :raises HTTPException: 404, if it isn't owned by the user.
    :return: the updated planned income.
    """
    try:
        return await planned_income_service.update(
            cast(User, user.unwrap()),
            planned_income_id,
            **repeat_fields(payload.model_dump(exclude_unset=True)),
        )
    except PlannedIncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Planned income not found."
        ) from exc
    except InvalidAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id must name one of your own accounts.",
        ) from exc
    except InvalidRepeatError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="repeat needs a weekly, monthly or yearly frequency and a date.",
        ) from exc


@router.delete("/{planned_income_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_planned_income(
    planned_income_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    planned_income_service: PlannedIncomeService = Depends(get_planned_income_service),
) -> None:
    """
    Delete a planned income owned by the current user.

    :param planned_income_id: planned income to delete.
    :param user: the authenticated user.
    :param planned_income_service: planned income service.
    :raises HTTPException: 404, if it isn't owned by the user.
    """
    try:
        await planned_income_service.delete(
            cast(User, user.unwrap()), planned_income_id
        )
    except PlannedIncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Planned income not found."
        ) from exc


@router.get(
    "/{planned_income_id}/candidates",
    response_model=list[PlannedIncomeCandidateRead],
)
async def list_planned_income_candidates(
    planned_income_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    planned_income_service: PlannedIncomeService = Depends(get_planned_income_service),
) -> list[Income]:
    """
    Suggest existing incomes a planned income could plausibly be realised against.

    :param planned_income_id: planned income to suggest candidates for.
    :param user: the authenticated user.
    :param planned_income_service: planned income service.
    :raises HTTPException: 404, if it isn't owned by the user.
    :return: candidate incomes, most recent first.
    """
    try:
        return await planned_income_service.list_realise_candidates(
            cast(User, user.unwrap()), planned_income_id
        )
    except PlannedIncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Planned income not found."
        ) from exc


@router.post("/{planned_income_id}/realise", response_model=PlannedIncomeRead)
async def realise_planned_income(
    planned_income_id: uuid.UUID,
    payload: PlannedIncomeRealise,
    user: RequestUser = Depends(require_auth),
    planned_income_service: PlannedIncomeService = Depends(get_planned_income_service),
) -> PlannedIncome:
    """
    Mark a planned income as received, linking it to a real income.

    :param planned_income_id: planned income being realised.
    :param payload: either ``existing_income_id``, or override fields
        (``account_id`` required) for a brand-new income.
    :param user: the authenticated user.
    :param planned_income_service: planned income service.
    :raises HTTPException: 404/400, see the service's own errors.
    :return: the realised planned income.
    """
    overrides = payload.model_dump(exclude={"existing_income_id"}, exclude_none=True)
    try:
        return await planned_income_service.realise(
            cast(User, user.unwrap()),
            planned_income_id,
            existing_income_id=payload.existing_income_id,
            income_overrides=overrides or None,
        )
    except PlannedIncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Planned income not found."
        ) from exc
    except InvalidIncomeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="existing_income_id must name one of your own incomes.",
        ) from exc
    except MissingAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id is required when creating a new income.",
        ) from exc
