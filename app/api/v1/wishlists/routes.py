import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.wishlists import get_wishlist_service
from app.api.v1.wishlists.schema import (
    WishlistCandidateSpentRead,
    WishlistCreate,
    WishlistItemCreate,
    WishlistItemRead,
    WishlistItemRealise,
    WishlistItemTransfer,
    WishlistItemUpdate,
    WishlistRead,
    WishlistUpdate,
)
from app.db.sql.models.spent import Spent
from app.db.sql.models.users import User
from app.db.sql.models.wishlist import Wishlist, WishlistItem
from app.services.plan_repeat import InvalidRepeatError, repeat_fields
from app.services.wishlist_service import (
    InvalidAccountError,
    InvalidSpentError,
    InvalidTargetWishlistError,
    MissingAccountError,
    WishlistNotFoundError,
    WishlistService,
)

router = APIRouter(prefix="/wishlists", tags=["wishlists"])


@router.get("", response_model=list[WishlistRead])
async def list_wishlists(
    scope: str = Query("me", pattern="^(me|family)$"),
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> list[Wishlist]:
    """
    List wishlists visible to the current user.

    :param scope: ``"me"`` or ``"family"``.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :return: matching wishlists.
    """
    return await wishlist_service.list_wishlists(cast(User, user.unwrap()), scope=scope)


@router.post("", response_model=WishlistRead, status_code=status.HTTP_201_CREATED)
async def create_wishlist(
    payload: WishlistCreate,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> Wishlist:
    """
    Create a wishlist owned by the current user.

    :param payload: wishlist-creation payload.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :return: the created wishlist.
    """
    return await wishlist_service.create_wishlist(
        cast(User, user.unwrap()),
        payload.name,
        description=payload.description,
        date_from=payload.date_from,
        date_to=payload.date_to,
        visibility=payload.visibility,
    )


@router.get("/{wishlist_id}", response_model=WishlistRead)
async def read_wishlist(
    wishlist_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> Wishlist:
    """
    Fetch a wishlist the current user is allowed to read.

    :param wishlist_id: wishlist to fetch.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :raises HTTPException: 404, if it doesn't exist or isn't visible.
    :return: the wishlist.
    """
    try:
        return await wishlist_service.get_visible(
            cast(User, user.unwrap()), wishlist_id
        )
    except WishlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist not found."
        ) from exc


@router.patch("/{wishlist_id}", response_model=WishlistRead)
async def update_wishlist(
    wishlist_id: uuid.UUID,
    payload: WishlistUpdate,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> Wishlist:
    """
    Update fields on a wishlist owned by the current user.

    :param wishlist_id: wishlist to update.
    :param payload: fields to change; omitted fields are left as-is.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :raises HTTPException: 404, if it isn't owned by the user.
    :return: the updated wishlist.
    """
    try:
        return await wishlist_service.update_wishlist(
            cast(User, user.unwrap()),
            wishlist_id,
            **payload.model_dump(exclude_unset=True),
        )
    except WishlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist not found."
        ) from exc


@router.delete("/{wishlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wishlist(
    wishlist_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> None:
    """
    Delete a wishlist owned by the current user, and its items.

    :param wishlist_id: wishlist to delete.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :raises HTTPException: 404, if it isn't owned by the user.
    """
    try:
        await wishlist_service.delete_wishlist(cast(User, user.unwrap()), wishlist_id)
    except WishlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist not found."
        ) from exc


@router.get("/{wishlist_id}/items", response_model=list[WishlistItemRead])
async def list_wishlist_items(
    wishlist_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> list[WishlistItem]:
    """
    List a wishlist's items, for anyone allowed to read the wishlist.

    :param wishlist_id: parent wishlist.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :raises HTTPException: 404, if the wishlist isn't visible.
    :return: its items.
    """
    try:
        return await wishlist_service.list_items(cast(User, user.unwrap()), wishlist_id)
    except WishlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist not found."
        ) from exc


@router.post(
    "/{wishlist_id}/items",
    response_model=WishlistItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_wishlist_item(
    wishlist_id: uuid.UUID,
    payload: WishlistItemCreate,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> WishlistItem:
    """
    Add a planned item to a wishlist owned by the current user.

    :param wishlist_id: parent wishlist.
    :param payload: item-creation payload.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :raises HTTPException: 404, if the wishlist isn't owned by the user.
    :return: the created item.
    """
    try:
        return await wishlist_service.add_item(
            cast(User, user.unwrap()),
            wishlist_id,
            category_id=payload.category_id,
            name=payload.name,
            amount=payload.amount,
            planned_date=payload.planned_date,
            planned_date_to=payload.planned_date_to,
            frequency=payload.frequency,
            repeat_until=payload.repeat_until,
            visibility=payload.visibility,
            account_id=payload.account_id,
        )
    except WishlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist not found."
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


@router.patch("/items/{item_id}", response_model=WishlistItemRead)
async def update_wishlist_item(
    item_id: uuid.UUID,
    payload: WishlistItemUpdate,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> WishlistItem:
    """
    Update a planned item on a wishlist owned by the current user.

    :param item_id: item to update.
    :param payload: fields to change; omitted fields are left as-is.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :raises HTTPException: 404, if it doesn't exist or isn't the user's.
    :return: the updated item.
    """
    try:
        return await wishlist_service.update_item(
            cast(User, user.unwrap()),
            item_id,
            **repeat_fields(payload.model_dump(exclude_unset=True)),
        )
    except WishlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
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


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wishlist_item(
    item_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> None:
    """
    Delete a planned item from a wishlist owned by the current user.

    :param item_id: item to delete.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :raises HTTPException: 404, if it doesn't exist or isn't the user's.
    """
    try:
        await wishlist_service.delete_item(cast(User, user.unwrap()), item_id)
    except WishlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        ) from exc


@router.post("/items/{item_id}/transfer", response_model=WishlistItemRead)
async def transfer_wishlist_item(
    item_id: uuid.UUID,
    payload: WishlistItemTransfer,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> WishlistItem:
    """
    Move a planned item to another wishlist the current user owns.

    :param item_id: item to move.
    :param payload: target wishlist id.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :raises HTTPException: 404/400, see the service's own errors.
    :return: the updated item.
    """
    try:
        return await wishlist_service.transfer_item(
            cast(User, user.unwrap()), item_id, payload.target_wishlist_id
        )
    except WishlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        ) from exc
    except InvalidTargetWishlistError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_wishlist_id must name one of your own wishlists.",
        ) from exc


@router.get(
    "/items/{item_id}/candidates",
    response_model=list[WishlistCandidateSpentRead],
)
async def list_wishlist_item_candidates(
    item_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> list[Spent]:
    """
    Suggest existing spents an item could plausibly be realised against.

    A ranking hint for the client's picker, not a correctness guarantee.

    :param item_id: item to suggest candidates for.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :raises HTTPException: 404, if the item isn't the user's.
    :return: candidate spents, most recent first.
    """
    try:
        return await wishlist_service.list_realise_candidates(
            cast(User, user.unwrap()), item_id
        )
    except WishlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        ) from exc


@router.post("/items/{item_id}/realise", response_model=WishlistItemRead)
async def realise_wishlist_item(
    item_id: uuid.UUID,
    payload: WishlistItemRealise,
    user: RequestUser = Depends(require_auth),
    wishlist_service: WishlistService = Depends(get_wishlist_service),
) -> WishlistItem:
    """
    Mark a planned item as bought, linking it to a real spent.

    :param item_id: item being realised.
    :param payload: either ``existing_spent_id``, or override fields
        (``account_id`` required) for a brand-new spent.
    :param user: the authenticated user.
    :param wishlist_service: wishlist service.
    :raises HTTPException: 404/400, see the service's own errors.
    :return: the realised item.
    """
    overrides = payload.model_dump(exclude={"existing_spent_id"}, exclude_none=True)
    try:
        return await wishlist_service.realise_item(
            cast(User, user.unwrap()),
            item_id,
            existing_spent_id=payload.existing_spent_id,
            spent_overrides=overrides or None,
        )
    except WishlistNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found."
        ) from exc
    except InvalidSpentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="existing_spent_id must name one of your own spents.",
        ) from exc
    except MissingAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id is required when creating a new spent.",
        ) from exc
