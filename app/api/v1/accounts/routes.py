import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.base.base import RequestUser
from app.api.dependencies.accounts import get_account_service
from app.api.dependencies.auth import require_auth
from app.api.v1.accounts.schema import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    BalanceAdjustmentRead,
    BalanceRead,
    BalanceSet,
)
from app.db.sql.models.account import Account, BalanceAdjustment
from app.db.sql.models.users import User
from app.services.account_service import (
    AccountInUseError,
    AccountNotOwnedError,
    AccountService,
    InvalidAccountSourceError,
    InvalidParentAccountError,
    NestedSubAccountError,
    SubAccountCannotImportError,
    UnknownAccountSourceError,
    UnsupportedCurrencyError,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])

_BAD_REQUEST_DETAILS: dict[type[Exception], str] = {
    InvalidAccountSourceError: "market_bill isn't a valid account source.",
    UnknownAccountSourceError: "source must be a known statement source.",
    UnsupportedCurrencyError: "currency must be one of the supported currencies.",
    InvalidParentAccountError: "parent_account_id must name one of your accounts.",
    NestedSubAccountError: "Sub-accounts can't be nested more than one level.",
    SubAccountCannotImportError: "A jar or card can't have an import source.",
}
_BAD_REQUEST_ERRORS = tuple(_BAD_REQUEST_DETAILS)


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=_BAD_REQUEST_DETAILS[type(exc)],
    )


@router.get("", response_model=list[AccountRead])
async def list_accounts(
    include_inactive: bool = Query(False),
    parent_account_id: uuid.UUID | None = Query(None),
    user: RequestUser = Depends(require_auth),
    account_service: AccountService = Depends(get_account_service),
) -> list[Account]:
    """
    List the current user's accounts.

    :param include_inactive: whether to include archived accounts.
    :param parent_account_id: restrict to one account's jars/cards.
    :param user: the authenticated user.
    :param account_service: account service.
    :return: matching accounts.
    """
    return await account_service.list_for_user(
        cast(User, user.unwrap()),
        include_inactive=include_inactive,
        parent_account_id=parent_account_id,
    )


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    user: RequestUser = Depends(require_auth),
    account_service: AccountService = Depends(get_account_service),
) -> Account:
    """
    Create an account owned by the current user.

    :param payload: account-creation payload.
    :param user: the authenticated user.
    :param account_service: account service.
    :raises HTTPException: 400, see the service's own errors.
    :return: the created account.
    """
    try:
        return await account_service.create(
            cast(User, user.unwrap()),
            payload.name,
            payload.kind,
            payload.currency,
            source=payload.source,
            opening_balance=payload.opening_balance,
            parent_account_id=payload.parent_account_id,
            is_savings=payload.is_savings,
        )
    except _BAD_REQUEST_ERRORS as exc:
        raise _bad_request(exc) from exc


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    user: RequestUser = Depends(require_auth),
    account_service: AccountService = Depends(get_account_service),
) -> Account:
    """
    Update fields on an account owned by the current user.

    :param account_id: account to update.
    :param payload: fields to change; omitted fields are left as-is.
    :param user: the authenticated user.
    :param account_service: account service.
    :raises HTTPException: 404/400, see the service's own errors.
    :return: the updated account.
    """
    try:
        return await account_service.update(
            cast(User, user.unwrap()),
            account_id,
            **payload.model_dump(exclude_unset=True),
        )
    except AccountNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        ) from exc
    except _BAD_REQUEST_ERRORS as exc:
        raise _bad_request(exc) from exc


@router.post("/{account_id}/archive", response_model=AccountRead)
async def archive_account(
    account_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    account_service: AccountService = Depends(get_account_service),
) -> Account:
    """
    Archive an account, hiding it from the default list without deleting it.

    :param account_id: account to archive.
    :param user: the authenticated user.
    :param account_service: account service.
    :raises HTTPException: 404, if the account isn't the user's.
    :return: the archived account.
    """
    try:
        return await account_service.archive(cast(User, user.unwrap()), account_id)
    except AccountNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        ) from exc


@router.post("/{account_id}/restore", response_model=AccountRead)
async def restore_account(
    account_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    account_service: AccountService = Depends(get_account_service),
) -> Account:
    """
    Bring an archived account back into active use.

    :param account_id: account to restore.
    :param user: the authenticated user.
    :param account_service: account service.
    :raises HTTPException: 404, if the account isn't the user's.
    :return: the restored account.
    """
    try:
        return await account_service.restore(cast(User, user.unwrap()), account_id)
    except AccountNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        ) from exc


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    account_service: AccountService = Depends(get_account_service),
) -> None:
    """
    Permanently delete an account that has no spent/income history.

    :param account_id: account to delete.
    :param user: the authenticated user.
    :param account_service: account service.
    :raises HTTPException: 404, if the account isn't the user's; 409, if
        it has entries -- archive it instead.
    """
    try:
        await account_service.delete(cast(User, user.unwrap()), account_id)
    except AccountNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        ) from exc
    except AccountInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Accounts with entries can't be deleted — archive them instead.",
        ) from exc


@router.get("/{account_id}/balance", response_model=BalanceRead)
async def read_balance(
    account_id: uuid.UUID,
    user: RequestUser = Depends(require_auth),
    account_service: AccountService = Depends(get_account_service),
) -> BalanceRead:
    """
    Return the current balance of one of the user's accounts.

    :param account_id: account to total.
    :param user: the authenticated user.
    :param account_service: account service.
    :raises HTTPException: 404, if the account isn't the user's.
    :return: the current balance.
    """
    try:
        balance = await account_service.current_balance(
            cast(User, user.unwrap()), account_id
        )
    except AccountNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        ) from exc
    return BalanceRead(current_balance=balance)


@router.post(
    "/{account_id}/balance",
    response_model=BalanceAdjustmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def set_balance(
    account_id: uuid.UUID,
    payload: BalanceSet,
    user: RequestUser = Depends(require_auth),
    account_service: AccountService = Depends(get_account_service),
) -> BalanceAdjustment:
    """
    Place an existing amount on an account by recording an adjustment.

    :param account_id: account to correct.
    :param payload: the balance the account should have.
    :param user: the authenticated user.
    :param account_service: account service.
    :raises HTTPException: 404, if the account isn't the user's.
    :return: the created adjustment.
    """
    try:
        return await account_service.set_balance(
            cast(User, user.unwrap()),
            account_id,
            payload.target_balance,
            as_of=payload.as_of,
            reason=payload.reason,
        )
    except AccountNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        ) from exc
