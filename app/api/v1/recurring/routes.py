import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.recurring import get_recurring_transaction_service
from app.api.v1.recurring.schema import (
    CompleteOccurrence,
    OccurrenceCompletedAtUpdate,
    RecurringOccurrenceRead,
    RecurringTransactionCreate,
    RecurringTransactionRead,
    RecurringTransactionUpdate,
)
from app.db.sql.models.enums import PlanStatus
from app.db.sql.models.recurring_transaction import (
    RecurringOccurrence,
    RecurringTransaction,
)
from app.db.sql.models.users import User
from app.services.recurring_transaction_service import (
    CategoryKindMismatchError,
    InvalidAccountError,
    InvalidLinkedRecordError,
    OccurrenceAlreadyCompletedError,
    OccurrenceNotCompletedError,
    OccurrenceNotFoundError,
    RecurringTransactionNotFoundError,
    RecurringTransactionService,
)

router = APIRouter(prefix="/recurring", tags=["recurring"])


@router.get("", response_model=list[RecurringTransactionRead])
async def list_recurring(
    scope: str = Query("me", pattern="^(me|family)$"),
    user: RequestUser = Depends(require_auth),
    recurring_service: RecurringTransactionService = Depends(
        get_recurring_transaction_service
    ),
) -> list[RecurringTransaction]:
    """
    List recurring transaction rules visible to the current user.

    :param scope: ``"me"`` or ``"family"``.
    :param user: the authenticated user.
    :param recurring_service: recurring transaction service.
    :return: matching rules.
    """
    return await recurring_service.list_recurring(
        cast(User, user.unwrap()), scope=scope
    )


@router.get("/occurrences", response_model=list[RecurringOccurrenceRead])
async def list_occurrences(
    scope: str = Query("me", pattern="^(me|family)$"),
    status_filter: PlanStatus | None = Query(None, alias="status"),
    user: RequestUser = Depends(require_auth),
    recurring_service: RecurringTransactionService = Depends(
        get_recurring_transaction_service
    ),
) -> list[RecurringOccurrence]:
    """
    List recurring occurrences: the confirmation queue and its history.

    :param scope: ``"me"`` or ``"family"``.
    :param status_filter: ``planned`` for the queue, ``realised`` for history.
    :param user: the authenticated user.
    :param recurring_service: recurring transaction service.
    :return: matching occurrences, earliest due date first.
    """
    return await recurring_service.list_occurrences(
        cast(User, user.unwrap()), scope=scope, status=status_filter
    )


@router.post(
    "/occurrences/{occurrence_id}/complete",
    response_model=RecurringOccurrenceRead,
)
async def complete_occurrence(
    occurrence_id: uuid.UUID,
    payload: CompleteOccurrence,
    user: RequestUser = Depends(require_auth),
    recurring_service: RecurringTransactionService = Depends(
        get_recurring_transaction_service
    ),
) -> RecurringOccurrence:
    """
    Confirm that an occurrence happened, posting or linking its record.

    :param occurrence_id: occurrence to confirm.
    :param payload: completion date, and an existing record or overrides.
    :param user: the authenticated user.
    :param recurring_service: recurring transaction service.
    :raises HTTPException: 404/409/400, see the service's own errors.
    :return: the confirmed occurrence.
    """
    overrides = payload.model_dump(
        exclude_none=True,
        include={"amount", "account_id", "category_id"},
    )
    try:
        return await recurring_service.complete_occurrence(
            cast(User, user.unwrap()),
            occurrence_id,
            completed_at=payload.completed_at,
            existing_spent_id=payload.existing_spent_id,
            existing_income_id=payload.existing_income_id,
            overrides=overrides,
        )
    except OccurrenceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Occurrence not found."
        ) from exc
    except OccurrenceAlreadyCompletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Occurrence is already completed.",
        ) from exc
    except InvalidLinkedRecordError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The linked record must be your own and match the rule's kind.",
        ) from exc
    except InvalidAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id must name one of your own accounts.",
        ) from exc


@router.patch("/occurrences/{occurrence_id}", response_model=RecurringOccurrenceRead)
async def edit_occurrence_completed_at(
    occurrence_id: uuid.UUID,
    payload: OccurrenceCompletedAtUpdate,
    user: RequestUser = Depends(require_auth),
    recurring_service: RecurringTransactionService = Depends(
        get_recurring_transaction_service
    ),
) -> RecurringOccurrence:
    """
    Edit the completion date of a confirmed occurrence.

    :param occurrence_id: occurrence to edit.
    :param payload: the corrected completion date.
    :param user: the authenticated user.
    :param recurring_service: recurring transaction service.
    :raises HTTPException: 404/409, see the service's own errors.
    :return: the updated occurrence.
    """
    try:
        return await recurring_service.update_completed_at(
            cast(User, user.unwrap()), occurrence_id, payload.completed_at
        )
    except OccurrenceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Occurrence not found."
        ) from exc
    except OccurrenceNotCompletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Occurrence hasn't been completed yet.",
        ) from exc


@router.post(
    "", response_model=RecurringTransactionRead, status_code=status.HTTP_201_CREATED
)
async def create_recurring(
    payload: RecurringTransactionCreate,
    user: RequestUser = Depends(require_auth),
    recurring_service: RecurringTransactionService = Depends(
        get_recurring_transaction_service
    ),
) -> RecurringTransaction:
    """
    Create a recurring transaction rule owned by the current user.

    :param payload: rule-creation payload.
    :param user: the authenticated user.
    :param recurring_service: recurring transaction service.
    :raises HTTPException: 400, see the service's own errors.
    :return: the created rule.
    """
    try:
        return await recurring_service.create(
            cast(User, user.unwrap()),
            account_id=payload.account_id,
            kind=payload.kind,
            category_id=payload.category_id,
            amount=payload.amount,
            frequency=payload.frequency,
            start_date=payload.start_date,
            interval=payload.interval,
            day_of_month=payload.day_of_month,
            weekday=payload.weekday,
            end_date=payload.end_date,
            description=payload.description,
            visibility=payload.visibility,
        )
    except InvalidAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id must name one of your own accounts.",
        ) from exc
    except CategoryKindMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="category_id must be a category of the given kind.",
        ) from exc


@router.patch("/{recurring_transaction_id}", response_model=RecurringTransactionRead)
async def update_recurring(
    recurring_transaction_id: uuid.UUID,
    payload: RecurringTransactionUpdate,
    user: RequestUser = Depends(require_auth),
    recurring_service: RecurringTransactionService = Depends(
        get_recurring_transaction_service
    ),
) -> RecurringTransaction:
    """
    Update fields on a recurring transaction rule owned by the current user.

    :param recurring_transaction_id: rule to update.
    :param payload: fields to change; omitted fields are left as-is.
    :param user: the authenticated user.
    :param recurring_service: recurring transaction service.
    :raises HTTPException: 404/400, see the service's own errors.
    :return: the updated rule.
    """
    try:
        return await recurring_service.update(
            cast(User, user.unwrap()),
            recurring_transaction_id,
            **payload.model_dump(exclude_unset=True),
        )
    except RecurringTransactionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found."
        ) from exc
    except InvalidAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id must name one of your own accounts.",
        ) from exc
    except CategoryKindMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="category_id must be a category of the given kind.",
        ) from exc


@router.delete("/{recurring_transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring(
    recurring_transaction_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    recurring_service: RecurringTransactionService = Depends(
        get_recurring_transaction_service
    ),
) -> None:
    """
    Delete a recurring transaction rule owned by the current user.

    :param recurring_transaction_id: rule to delete.
    :param user: the authenticated user.
    :param recurring_service: recurring transaction service.
    :raises HTTPException: 404, if it isn't owned by the user.
    """
    try:
        await recurring_service.delete(
            cast(User, user.unwrap()), recurring_transaction_id
        )
    except RecurringTransactionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found."
        ) from exc


@router.post(
    "/{recurring_transaction_id}/pause", response_model=RecurringTransactionRead
)
async def pause_recurring(
    recurring_transaction_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    recurring_service: RecurringTransactionService = Depends(
        get_recurring_transaction_service
    ),
) -> RecurringTransaction:
    """
    Pause a recurring transaction rule without deleting it.

    :param recurring_transaction_id: rule to pause.
    :param user: the authenticated user.
    :param recurring_service: recurring transaction service.
    :raises HTTPException: 404, if it isn't owned by the user.
    :return: the paused rule.
    """
    try:
        return await recurring_service.pause(
            cast(User, user.unwrap()), recurring_transaction_id
        )
    except RecurringTransactionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found."
        ) from exc


@router.post(
    "/{recurring_transaction_id}/resume", response_model=RecurringTransactionRead
)
async def resume_recurring(
    recurring_transaction_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    recurring_service: RecurringTransactionService = Depends(
        get_recurring_transaction_service
    ),
) -> RecurringTransaction:
    """
    Resume a paused recurring transaction rule.

    :param recurring_transaction_id: rule to resume.
    :param user: the authenticated user.
    :param recurring_service: recurring transaction service.
    :raises HTTPException: 404, if it isn't owned by the user.
    :return: the resumed rule.
    """
    try:
        return await recurring_service.resume(
            cast(User, user.unwrap()), recurring_transaction_id
        )
    except RecurringTransactionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found."
        ) from exc
