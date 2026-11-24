import uuid
from datetime import date
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.transfers import get_transfer_service
from app.api.v1.transfers.schema import TransferCreate, TransferRead, TransferUpdate
from app.db.sql.models.transfer import Transfer
from app.db.sql.models.users import User
from app.services.transfer_service import (
    AmbiguousTransferAmountError,
    InvalidAccountError,
    InvalidTransferTargetError,
    TransferNotFoundError,
    TransferService,
)

router = APIRouter(prefix="/transfers", tags=["transfers"])

_BAD_REQUEST_DETAILS: dict[type[Exception], str] = {
    InvalidAccountError: "from_account_id must name one of your own accounts.",
    InvalidTransferTargetError: (
        "to_account_id must be a different account in your household."
    ),
    AmbiguousTransferAmountError: (
        "to_amount is required when the accounts use different currencies."
    ),
}
_BAD_REQUEST_ERRORS = tuple(_BAD_REQUEST_DETAILS)


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=_BAD_REQUEST_DETAILS[type(exc)],
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found."
    )


@router.get("", response_model=list[TransferRead])
async def list_transfers(
    scope: str = Query("me", pattern="^(me|family)$"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    user: RequestUser = Depends(require_auth),
    transfer_service: TransferService = Depends(get_transfer_service),
) -> list[Transfer]:
    """
    List transfers visible to the current user.

    :param scope: ``"me"`` or ``"family"``.
    :param date_from: earliest date to include, inclusive.
    :param date_to: latest date to include, inclusive.
    :param user: the authenticated user.
    :param transfer_service: transfer service.
    :return: matching transfers.
    """
    return await transfer_service.list_transfers(
        cast(User, user.unwrap()), scope=scope, date_from=date_from, date_to=date_to
    )


@router.post("", response_model=TransferRead, status_code=status.HTTP_201_CREATED)
async def create_transfer(
    payload: TransferCreate,
    user: RequestUser = Depends(require_auth),
    transfer_service: TransferService = Depends(get_transfer_service),
) -> Transfer:
    """
    Move money between two accounts in the current user's household.

    :param payload: transfer-creation payload.
    :param user: the authenticated user.
    :param transfer_service: transfer service.
    :raises HTTPException: 400, see the service's own errors.
    :return: the created transfer.
    """
    try:
        return await transfer_service.create(
            cast(User, user.unwrap()), **payload.model_dump()
        )
    except _BAD_REQUEST_ERRORS as exc:
        raise _bad_request(exc) from exc


@router.get("/{transfer_id}", response_model=TransferRead)
async def read_transfer(
    transfer_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    transfer_service: TransferService = Depends(get_transfer_service),
) -> Transfer:
    """
    Fetch one transfer the current user may read.

    :param transfer_id: transfer to fetch.
    :param user: the authenticated user.
    :param transfer_service: transfer service.
    :raises HTTPException: 404, if it doesn't exist or isn't visible.
    :return: the transfer.
    """
    try:
        return await transfer_service.get_visible(
            cast(User, user.unwrap()), transfer_id
        )
    except TransferNotFoundError as exc:
        raise _not_found() from exc


@router.patch("/{transfer_id}", response_model=TransferRead)
async def update_transfer(
    transfer_id: uuid.UUID,
    payload: TransferUpdate,
    user: RequestUser = Depends(require_auth),
    transfer_service: TransferService = Depends(get_transfer_service),
) -> Transfer:
    """
    Update fields on a transfer owned by the current user.

    :param transfer_id: transfer to update.
    :param payload: fields to change; omitted fields are left as-is.
    :param user: the authenticated user.
    :param transfer_service: transfer service.
    :raises HTTPException: 404/400, see the service's own errors.
    :return: the updated transfer.
    """
    try:
        return await transfer_service.update(
            cast(User, user.unwrap()),
            transfer_id,
            **payload.model_dump(exclude_unset=True),
        )
    except TransferNotFoundError as exc:
        raise _not_found() from exc
    except _BAD_REQUEST_ERRORS as exc:
        raise _bad_request(exc) from exc


@router.delete("/{transfer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transfer(
    transfer_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    transfer_service: TransferService = Depends(get_transfer_service),
) -> None:
    """
    Delete a transfer owned by the current user.

    :param transfer_id: transfer to delete.
    :param user: the authenticated user.
    :param transfer_service: transfer service.
    :raises HTTPException: 404, if it isn't owned by the user.
    """
    try:
        await transfer_service.delete(cast(User, user.unwrap()), transfer_id)
    except TransferNotFoundError as exc:
        raise _not_found() from exc
