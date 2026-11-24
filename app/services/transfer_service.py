import uuid
from datetime import date
from decimal import Decimal
from typing import cast

from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.account_query import AccountQuery
from app.dal.transfer_query import TransferQuery
from app.db.sql.models.account import Account
from app.db.sql.models.enums import Visibility
from app.db.sql.models.transfer import Transfer
from app.db.sql.models.users import User
from app.services.visibility_service import VisibilityService


class TransferNotFoundError(Exception):
    """Raised when a transfer isn't visible/owned."""


class InvalidAccountError(Exception):
    """Raised when the source account isn't owned by the actor."""


class InvalidTransferTargetError(Exception):
    """Raised when the destination isn't a household account (or is the source)."""


class AmbiguousTransferAmountError(Exception):
    """Raised when a cross-currency transfer doesn't state what arrived."""


class TransferService:
    """
    Business logic for moving money between household accounts.

    A transfer never counts as spending or income -- it only moves money
    inside the household, so it lives in its own table.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.transfers = TransferQuery(session)
        self.account_queries = AccountQuery(session)

    async def _resolve_accounts(
        self,
        actor: User,
        from_account_id: uuid.UUID,
        to_account_id: uuid.UUID,
    ) -> tuple[Account, Account]:
        source = await self.account_queries.get(from_account_id)
        if source is None or source.user_id != actor.id:
            raise InvalidAccountError
        target = await self.account_queries.get(to_account_id)
        if target is None or to_account_id == from_account_id:
            raise InvalidTransferTargetError
        household = await VisibilityService(actor.id, self.session).visible_owner_ids(
            scope="family"
        )
        if target.user_id not in household:
            raise InvalidTransferTargetError
        return source, target

    @staticmethod
    def _resolve_to_amount(
        source: Account, target: Account, amount: Decimal, to_amount: Decimal | None
    ) -> Decimal:
        if to_amount is not None:
            return to_amount
        # Never auto-converted: the real cross-currency rate is whatever the
        # provider charged, which a stored market rate doesn't promise.
        if source.currency != target.currency:
            raise AmbiguousTransferAmountError
        return amount

    async def create(
        self,
        actor: User,
        *,
        from_account_id: uuid.UUID,
        to_account_id: uuid.UUID,
        amount: Decimal,
        transferred_at: date,
        to_amount: Decimal | None = None,
        description: str | None = None,
        visibility: Visibility = Visibility.PRIVATE,
    ) -> Transfer:
        """
        Move money from one of ``actor``'s accounts to a household account.

        :param actor: the transfer's owner.
        :param from_account_id: source account -- must belong to ``actor``.
        :param to_account_id: destination -- ``actor``'s or a family member's.
        :param amount: amount leaving the source, in its currency.
        :param transferred_at: date it happened.
        :param to_amount: amount arriving, in the destination's currency;
            defaults to ``amount`` for same-currency accounts, required
            otherwise.
        :param description: free-text note.
        :param visibility: who besides ``actor`` may see it.
        :raises InvalidAccountError: if the source isn't ``actor``'s.
        :raises InvalidTransferTargetError: if the destination isn't in the
            household, or is the source itself.
        :raises AmbiguousTransferAmountError: if the currencies differ and
            ``to_amount`` wasn't given.
        :return: the created transfer.
        """
        source, target = await self._resolve_accounts(
            actor, from_account_id, to_account_id
        )
        return await self.transfers.create(
            user_id=actor.id,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount=amount,
            to_amount=self._resolve_to_amount(source, target, amount, to_amount),
            description=description,
            transferred_at=transferred_at,
            visibility=visibility,
        )

    async def _get_owned(self, actor: User, transfer_id: uuid.UUID) -> Transfer:
        transfer = await self.transfers.get(transfer_id)
        if transfer is None or transfer.user_id != actor.id:
            raise TransferNotFoundError
        return transfer

    async def get_visible(self, actor: User, transfer_id: uuid.UUID) -> Transfer:
        """
        Fetch a transfer ``actor`` is allowed to read.

        :param actor: user requesting the transfer.
        :param transfer_id: transfer to fetch.
        :raises TransferNotFoundError: if it doesn't exist or isn't visible.
        :return: the transfer.
        """
        transfer = await self.transfers.get(transfer_id)
        if transfer is None:
            raise TransferNotFoundError
        visibility_service = VisibilityService(actor.id, self.session)
        if not await visibility_service.can_view(transfer.user_id, transfer.visibility):
            raise TransferNotFoundError
        return transfer

    async def update(
        self, actor: User, transfer_id: uuid.UUID, **fields: object
    ) -> Transfer:
        """
        Update fields on a transfer owned by ``actor``.

        :param actor: user requesting the update.
        :param transfer_id: transfer to update.
        :param fields: field values to set.
        :raises TransferNotFoundError: if it isn't owned by ``actor``.
        :raises InvalidAccountError: if the source isn't ``actor``'s.
        :raises InvalidTransferTargetError: if the destination is invalid.
        :raises AmbiguousTransferAmountError: if the currencies differ and
            no ``to_amount`` is known.
        :return: the updated transfer.
        """
        transfer = await self._get_owned(actor, transfer_id)
        accounts_changed = "from_account_id" in fields or "to_account_id" in fields
        if accounts_changed or "amount" in fields or "to_amount" in fields:
            from_id = cast(
                uuid.UUID, fields.get("from_account_id", transfer.from_account_id)
            )
            to_id = cast(uuid.UUID, fields.get("to_account_id", transfer.to_account_id))
            amount = cast(Decimal, fields.get("amount", transfer.amount))
            source, target = await self._resolve_accounts(actor, from_id, to_id)
            explicit = cast(Decimal | None, fields.get("to_amount"))
            if explicit is None and not accounts_changed and "amount" not in fields:
                explicit = transfer.to_amount
            fields["to_amount"] = self._resolve_to_amount(
                source, target, amount, explicit
            )
        return cast(Transfer, await self.transfers.update(transfer_id, **fields))

    async def delete(self, actor: User, transfer_id: uuid.UUID) -> None:
        """
        Delete a transfer owned by ``actor``.

        :param actor: user requesting the deletion.
        :param transfer_id: transfer to delete.
        :raises TransferNotFoundError: if it isn't owned by ``actor``.
        """
        await self._get_owned(actor, transfer_id)
        await self.transfers.delete(transfer_id)

    async def list_transfers(
        self,
        actor: User,
        *,
        scope: str = "me",
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Transfer]:
        """
        List transfers visible to ``actor``.

        :param actor: user requesting the list.
        :param scope: ``"me"`` or ``"family"``.
        :param date_from: earliest ``transferred_at``, inclusive.
        :param date_to: latest ``transferred_at``, inclusive.
        :return: matching transfers, most recent first.
        """
        owner_ids = await VisibilityService(actor.id, self.session).visible_owner_ids(
            scope=scope
        )
        return await self.transfers.list_for_range(
            actor.id, owner_ids, date_from=date_from, date_to=date_to
        )
