import uuid
from datetime import date
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.spents import get_spent_service
from app.api.v1.spents.schema import (
    SpentCreate,
    SpentDetailRead,
    SpentItemCreate,
    SpentItemRead,
    SpentItemUpdate,
    SpentRead,
    SpentUpdate,
)
from app.db.sql.models.spent import Spent, SpentItem
from app.db.sql.models.users import User
from app.services.spent_service import (
    InvalidAccountError,
    SpentNotFoundError,
    SpentService,
)

router = APIRouter(prefix="/spents", tags=["spents"])


def _spent_to_read(spent: Spent, *, item_count: int) -> SpentRead:
    return SpentRead(
        id=spent.id,
        user_id=spent.user_id,
        account_id=spent.account_id,
        category_id=spent.category_id,
        amount=spent.amount,
        description=spent.description,
        spent_at=spent.spent_at,
        visibility=spent.visibility,
        item_count=item_count,
        wishlist_item_id=spent.wishlist_item_id,
        recurring_occurrence_id=spent.recurring_occurrence_id,
    )


async def _to_read(spent_service: SpentService, spents: list[Spent]) -> list[SpentRead]:
    counts = await spent_service.item_counts([spent.id for spent in spents])
    return [
        _spent_to_read(spent, item_count=counts.get(spent.id, 0)) for spent in spents
    ]


@router.get("", response_model=list[SpentRead])
async def list_spents(
    *,
    scope: str = Query("me", pattern="^(me|family)$"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    category_id: int | None = Query(None),
    account_id: uuid.UUID | None = Query(None),
    user: RequestUser = Depends(require_auth),
    spent_service: SpentService = Depends(get_spent_service),
) -> list[SpentRead]:
    """
    List spents visible to the current user.

    :param scope: ``"me"`` or ``"family"``.
    :param date_from: earliest date to include, inclusive.
    :param date_to: latest date to include, inclusive.
    :param category_id: restrict to one category.
    :param account_id: restrict to one account.
    :param user: the authenticated user.
    :param spent_service: spent service.
    :return: matching spents, each with its line-item count.
    """
    spents = await spent_service.list_spents(
        cast(User, user.unwrap()),
        scope=scope,
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        account_id=account_id,
    )
    return await _to_read(spent_service, spents)


@router.post("", response_model=SpentRead, status_code=status.HTTP_201_CREATED)
async def create_spent(
    payload: SpentCreate,
    user: RequestUser = Depends(require_auth),
    spent_service: SpentService = Depends(get_spent_service),
) -> Spent:
    """
    Log a new spent for the current user.

    :param payload: spent-creation payload.
    :param user: the authenticated user.
    :param spent_service: spent service.
    :raises HTTPException: 400, if ``account_id`` isn't the user's.
    :return: the created spent.
    """
    try:
        return await spent_service.create(
            cast(User, user.unwrap()),
            account_id=payload.account_id,
            category_id=payload.category_id,
            amount=payload.amount,
            spent_at=payload.spent_at,
            description=payload.description,
            visibility=payload.visibility,
        )
    except InvalidAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id must name one of your own accounts.",
        ) from exc


@router.get("/{spent_id}", response_model=SpentDetailRead)
async def read_spent(
    spent_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    spent_service: SpentService = Depends(get_spent_service),
) -> SpentDetailRead:
    """
    Fetch a spent's full detail, including its line items.

    :param spent_id: spent to fetch.
    :param user: the authenticated user.
    :param spent_service: spent service.
    :raises HTTPException: 404, if it doesn't exist or isn't visible.
    :return: the spent, its line items, and their total.
    """
    try:
        spent = await spent_service.get_visible(cast(User, user.unwrap()), spent_id)
    except SpentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Spent not found."
        ) from exc
    items = await spent_service.list_items(cast(User, user.unwrap()), spent_id)
    items_total = await spent_service.items_total(spent_id)
    base = _spent_to_read(spent, item_count=len(items))
    return SpentDetailRead(
        **base.model_dump(),
        items=[SpentItemRead.model_validate(item) for item in items],
        items_total=items_total,
    )


@router.patch("/{spent_id}", response_model=SpentRead)
async def update_spent(
    spent_id: uuid.UUID,
    payload: SpentUpdate,
    user: RequestUser = Depends(require_auth),
    spent_service: SpentService = Depends(get_spent_service),
) -> SpentRead:
    """
    Update fields on a spent owned by the current user.

    :param spent_id: spent to update.
    :param payload: fields to change; omitted fields are left as-is.
    :param user: the authenticated user.
    :param spent_service: spent service.
    :raises HTTPException: 404/400, see the service's own errors.
    :return: the updated spent.
    """
    try:
        spent = await spent_service.update(
            cast(User, user.unwrap()),
            spent_id,
            **payload.model_dump(exclude_unset=True),
        )
    except SpentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Spent not found."
        ) from exc
    except InvalidAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id must name one of your own accounts.",
        ) from exc
    return (await _to_read(spent_service, [spent]))[0]


@router.delete("/{spent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_spent(
    spent_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    spent_service: SpentService = Depends(get_spent_service),
) -> None:
    """
    Delete a spent owned by the current user.

    :param spent_id: spent to delete.
    :param user: the authenticated user.
    :param spent_service: spent service.
    :raises HTTPException: 404, if it isn't owned by the user.
    """
    try:
        await spent_service.delete(cast(User, user.unwrap()), spent_id)
    except SpentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Spent not found."
        ) from exc


@router.post(
    "/{spent_id}/items",
    response_model=SpentItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_spent_item(
    spent_id: uuid.UUID,
    payload: SpentItemCreate,
    user: RequestUser = Depends(require_auth),
    spent_service: SpentService = Depends(get_spent_service),
) -> SpentItem:
    """
    Attach a line item to a spent owned by the current user.

    :param spent_id: parent spent.
    :param payload: line-item creation payload.
    :param user: the authenticated user.
    :param spent_service: spent service.
    :raises HTTPException: 404, if the spent isn't owned by the user.
    :return: the created line item.
    """
    try:
        return await spent_service.add_item(
            cast(User, user.unwrap()),
            spent_id,
            name=payload.name,
            amount=payload.amount,
            category_id=payload.category_id,
            quantity=payload.quantity,
        )
    except SpentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Spent not found."
        ) from exc


@router.patch("/items/{item_id}", response_model=SpentItemRead)
async def update_spent_item(
    item_id: uuid.UUID,
    payload: SpentItemUpdate,
    user: RequestUser = Depends(require_auth),
    spent_service: SpentService = Depends(get_spent_service),
) -> SpentItem:
    """
    Update a line item belonging to a spent owned by the current user.

    :param item_id: line item to update.
    :param payload: fields to change; omitted fields are left as-is.
    :param user: the authenticated user.
    :param spent_service: spent service.
    :raises HTTPException: 404, if it doesn't exist or isn't the user's.
    :return: the updated line item.
    """
    try:
        return await spent_service.update_item(
            cast(User, user.unwrap()),
            item_id,
            **payload.model_dump(exclude_unset=True),
        )
    except SpentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found."
        ) from exc


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_spent_item(
    item_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    spent_service: SpentService = Depends(get_spent_service),
) -> None:
    """
    Delete a line item belonging to a spent owned by the current user.

    :param item_id: line item to delete.
    :param user: the authenticated user.
    :param spent_service: spent service.
    :raises HTTPException: 404, if it doesn't exist or isn't the user's.
    """
    try:
        await spent_service.delete_item(cast(User, user.unwrap()), item_id)
    except SpentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found."
        ) from exc
