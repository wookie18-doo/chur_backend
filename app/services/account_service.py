import uuid
from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.account_query import AccountQuery
from app.dal.balance_adjustment_query import BalanceAdjustmentQuery
from app.dal.currency_query import CurrencyQuery
from app.dal.income_query import IncomeQuery
from app.dal.spent_query import SpentQuery
from app.dal.transfer_query import TransferQuery
from app.db.sql.models.account import Account, BalanceAdjustment
from app.db.sql.models.enums import AccountKind, Visibility
from app.db.sql.models.users import User
from app.services.statement_source_service import (
    MARKET_BILL_CODE,
    StatementSourceService,
)
from app.services.visibility_service import VisibilityService


class AccountNotOwnedError(Exception):
    """Raised when a user acts on an account they don't own."""


class AccountInUseError(Exception):
    """Raised when an account can't be deleted because it has entries."""


class InvalidAccountSourceError(Exception):
    """Raised when an account's ``source`` would be ``market_bill``."""


class UnknownAccountSourceError(Exception):
    """Raised when an account's ``source`` names no known statement source."""


class AccountHasNoImportSourceError(Exception):
    """Raised when a statement import is started against an unfed account."""


class UnsupportedCurrencyError(Exception):
    """Raised when an account's currency isn't an active ``Currency``."""


class InvalidParentAccountError(Exception):
    """Raised when a parent account is missing, foreign, or the account itself."""


class NestedSubAccountError(Exception):
    """Raised when sub-accounts would nest more than one level deep."""


class SubAccountCannotImportError(Exception):
    """Raised when an import ``source`` is set on a jar/card."""


class AccountService:
    """
    Business logic for a user's bank accounts, cards, and cash wallets.

    Builds its own :class:`~app.dal.account_query.AccountQuery` from the
    db session it's given -- callers never construct a query object
    themselves.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.accounts = AccountQuery(session)
        self.currencies = CurrencyQuery(session)
        self.spents = SpentQuery(session)
        self.incomes = IncomeQuery(session)
        self.transfers = TransferQuery(session)
        self.adjustments = BalanceAdjustmentQuery(session)
        self.source_service = StatementSourceService(session)
        self.session = session

    async def _resolve_source(self, code: str | None) -> int | None:
        if code is None:
            return None
        if code == MARKET_BILL_CODE:
            raise InvalidAccountSourceError
        source = await self.source_service.get_by_code(code)
        if source is None:
            raise UnknownAccountSourceError
        return source.id

    async def _check_currency(self, currency: str) -> None:
        active = {c.code for c in await self.currencies.list_active()}
        if currency not in active:
            raise UnsupportedCurrencyError

    async def _check_parent(
        self, user: User, parent_account_id: uuid.UUID, *, child_id: uuid.UUID | None
    ) -> None:
        if parent_account_id == child_id:
            raise InvalidParentAccountError
        parent = await self.accounts.get(parent_account_id)
        if parent is None or parent.user_id != user.id:
            raise InvalidParentAccountError
        if parent.parent_account_id is not None:
            raise NestedSubAccountError
        if child_id is not None and await self.accounts.retrieve(
            parent_account_id=child_id
        ):
            raise NestedSubAccountError

    async def create(
        self,
        user: User,
        name: str,
        kind: AccountKind,
        currency: str,
        *,
        source: str | None = None,
        opening_balance: Decimal | None = None,
        parent_account_id: uuid.UUID | None = None,
        is_savings: bool = False,
    ) -> Account:
        """
        Create an account owned by ``user``.

        :param user: the account's owner.
        :param name: user-given label.
        :param kind: bank/cash/card/broker/other.
        :param currency: ISO 4217 currency code.
        :param source: code of the automated import feed, if any.
        :param opening_balance: starting balance, if any.
        :param parent_account_id: the bank/broker this jar or card sits
            under, if any.
        :param is_savings: whether this is a savings destination.
        :raises InvalidAccountSourceError: if ``source`` is ``market_bill``
            -- that value only ever describes an ``ImportJob``.
        :raises UnknownAccountSourceError: if ``source`` matches no known
            statement source.
        :raises UnsupportedCurrencyError: if ``currency`` isn't active.
        :raises InvalidParentAccountError: if the parent isn't ``user``'s.
        :raises NestedSubAccountError: if the parent is itself a sub-account.
        :raises SubAccountCannotImportError: if a sub-account has a ``source``.
        :return: the created account.
        """
        source_id = await self._resolve_source(source)
        await self._check_currency(currency)
        if parent_account_id is not None:
            if source is not None:
                raise SubAccountCannotImportError
            await self._check_parent(user, parent_account_id, child_id=None)
        account = await self.accounts.create(
            user_id=user.id,
            name=name,
            kind=kind,
            currency=currency,
            source_id=source_id,
            opening_balance=opening_balance,
            parent_account_id=parent_account_id,
            is_savings=is_savings,
        )
        await self.accounts.session.refresh(account)
        return account

    async def _get_owned(self, user: User, account_id: uuid.UUID) -> Account:
        account = await self.accounts.get(account_id)
        if account is None or account.user_id != user.id:
            raise AccountNotOwnedError
        return account

    async def update(
        self, user: User, account_id: uuid.UUID, **fields: object
    ) -> Account:
        """
        Update fields on an account owned by ``user``.

        :param user: user requesting the update.
        :param account_id: account to update.
        :param fields: field values to set.
        :raises AccountNotOwnedError: if the account isn't ``user``'s.
        :raises InvalidAccountSourceError: if ``source`` is set to
            ``market_bill``.
        :raises UnknownAccountSourceError: if ``source`` matches no known
            statement source.
        :raises UnsupportedCurrencyError: if ``currency`` isn't active.
        :raises InvalidParentAccountError: if the new parent isn't ``user``'s.
        :raises NestedSubAccountError: if the change would nest sub-accounts.
        :raises SubAccountCannotImportError: if a sub-account ends up with a
            ``source``.
        :return: the updated account.
        """
        account = await self._get_owned(user, account_id)
        if "source" in fields:
            code = cast(str | None, fields.pop("source"))
            fields["source_id"] = await self._resolve_source(code)
        if fields.get("currency") is not None:
            await self._check_currency(str(fields["currency"]))
        parent_id = fields.get("parent_account_id", account.parent_account_id)
        if parent_id is not None:
            if fields.get("source_id", account.source_id) is not None:
                raise SubAccountCannotImportError
            if "parent_account_id" in fields:
                await self._check_parent(
                    user, cast(uuid.UUID, parent_id), child_id=account_id
                )
        # _get_owned above already confirmed the row exists.
        updated = cast(Account, await self.accounts.update(account_id, **fields))
        await self.accounts.session.refresh(updated)
        return updated

    async def archive(self, user: User, account_id: uuid.UUID) -> Account:
        """
        Mark an account as no longer in use, without deleting its history.

        :param user: user requesting the archive.
        :param account_id: account to archive.
        :raises AccountNotOwnedError: if the account isn't ``user``'s.
        :return: the archived account.
        """
        return await self.update(user, account_id, is_active=False)

    async def restore(self, user: User, account_id: uuid.UUID) -> Account:
        """
        Bring an archived account back into active use.

        :param user: user requesting the restore.
        :param account_id: account to restore.
        :raises AccountNotOwnedError: if the account isn't ``user``'s.
        :return: the restored account.
        """
        return await self.update(user, account_id, is_active=True)

    async def delete(self, user: User, account_id: uuid.UUID) -> None:
        """
        Permanently delete an account that has no spent/income history.

        :param user: user requesting the deletion.
        :param account_id: account to delete.
        :raises AccountNotOwnedError: if the account isn't ``user``'s.
        :raises AccountInUseError: if a spent/income still references it
            -- archive it instead.
        """
        await self._get_owned(user, account_id)
        try:
            await self.accounts.delete(account_id)
        except IntegrityError as exc:
            # The failed flush leaves the session's transaction aborted at
            # the DBAPI level -- roll back so it's usable again afterward
            # (request-scoped commit, or the next op in the same test).
            await self.accounts.session.rollback()
            raise AccountInUseError from exc

    async def list_for_user(
        self,
        user: User,
        *,
        scope: str = "family",
        include_inactive: bool = False,
        parent_account_id: uuid.UUID | None = None,
    ) -> list[Account]:
        """
        List the accounts ``user`` may see.

        :param user: user requesting the list.
        :param scope: ``"me"`` for just ``user``'s own accounts,
            ``"family"`` for every family member's (falls back to just
            ``user``'s if they aren't in a family).
        :param include_inactive: whether to include archived accounts.
        :param parent_account_id: restrict to one account's jars/cards.
        :return: matching accounts.
        """
        owner_ids = await VisibilityService(user.id, self.session).visible_owner_ids(
            scope=scope
        )
        accounts = await self.accounts.list_for_users(
            owner_ids, include_inactive=include_inactive
        )
        if parent_account_id is not None:
            accounts = [a for a in accounts if a.parent_account_id == parent_account_id]
        return accounts

    async def current_balance(self, user: User, account_id: uuid.UUID) -> Decimal:
        """
        Compute today's balance of an account ``user`` may see.

        ``opening_balance + incomes - spents + transfers in - transfers out
        + adjustments``, all for that literal account -- never rolled up
        into a parent's total.

        :param user: the account's owner or a member of their family.
        :param account_id: account to total.
        :raises AccountNotOwnedError: if ``user`` may not see the account.
        :return: the current balance.
        """
        account = await self._get_visible(user, account_id)
        return await self._balance_of(account)

    async def set_balance(
        self,
        user: User,
        account_id: uuid.UUID,
        target_balance: Decimal,
        *,
        as_of: date | None = None,
        reason: str | None = None,
    ) -> BalanceAdjustment:
        """
        Make the account's balance equal ``target_balance``.

        Records the difference as a new append-only adjustment, so the
        caller states what the balance should be, not the delta.

        :param user: the account's owner.
        :param account_id: account to correct.
        :param target_balance: what the balance should be now.
        :param as_of: date of the adjustment; defaults to today.
        :param reason: free-text note.
        :raises AccountNotOwnedError: if the account isn't ``user``'s.
        :return: the created adjustment.
        """
        account = await self._get_owned(user, account_id)
        delta = target_balance - await self._balance_of(account)
        return await self.adjustments.create(
            user_id=user.id,
            account_id=account_id,
            delta=delta,
            reason=reason,
            adjusted_at=as_of or date.today(),
        )

    async def require_import_source(self, user: User, account_id: uuid.UUID) -> Account:
        """
        Fetch an account owned by ``user``, requiring it to feed imports.

        :param user: user starting the import.
        :param account_id: account the statement belongs to.
        :raises AccountNotOwnedError: if the account isn't ``user``'s.
        :raises AccountHasNoImportSourceError: if the account has no
            ``source`` configured (e.g. a manually-tracked cash wallet).
        :return: the account, guaranteed to have a non-``None`` ``source``.
        """
        account = await self._get_owned(user, account_id)
        if account.source is None:
            raise AccountHasNoImportSourceError
        return account

    async def _get_visible(self, user: User, account_id: uuid.UUID) -> Account:
        account = await self.accounts.get(account_id)
        if account is None:
            raise AccountNotOwnedError
        visibility = VisibilityService(user.id, self.session)
        # Accounts have no visibility column: every one is family-readable.
        if not await visibility.can_view(account.user_id, Visibility.FAMILY):
            raise AccountNotOwnedError
        return account

    async def _balance_of(self, account: Account) -> Decimal:
        return (
            (account.opening_balance or Decimal(0))
            + await self.incomes.sum_for_account(account.id)
            - await self.spents.sum_for_account(account.id)
            + await self.transfers.sum_in(account.id)
            - await self.transfers.sum_out(account.id)
            + await self.adjustments.sum_for_account(account.id)
        )
