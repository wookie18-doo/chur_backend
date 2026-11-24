"""Router in front of the concrete transfer DAO."""

import uuid
from datetime import date
from decimal import Decimal

from sqlmodel import col, func, or_, select

from app.dal.sql.transfer_dao import TransferDAO
from app.db.sql.models.account import Account
from app.db.sql.models.enums import Visibility
from app.db.sql.models.transfer import Transfer


class TransferQuery(TransferDAO):
    """Everything ``TransferService`` needs to read and write transfers."""

    async def list_for_range(
        self,
        requester_id: uuid.UUID,
        owner_ids: set[uuid.UUID],
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Transfer]:
        """
        Fetch transfers visible to ``requester_id`` among ``owner_ids``.

        Same visibility rule as ``SpentQuery.list_for_range``.

        :param requester_id: user asking for the list.
        :param owner_ids: owners whose transfers are in scope.
        :param date_from: earliest ``transferred_at``, inclusive.
        :param date_to: latest ``transferred_at``, inclusive.
        :return: matching transfers, most recent first.
        """
        query = (
            select(Transfer)
            .where(col(Transfer.user_id).in_(owner_ids))
            .where(
                or_(
                    Transfer.user_id == requester_id,
                    Transfer.visibility == Visibility.FAMILY,
                )
            )
        )
        if date_from is not None:
            query = query.where(col(Transfer.transferred_at) >= date_from)
        if date_to is not None:
            query = query.where(col(Transfer.transferred_at) <= date_to)
        query = query.order_by(col(Transfer.transferred_at).desc())
        result = await self.session.exec(query)
        return list(result.all())

    async def sum_in(self, account_id: uuid.UUID) -> Decimal:
        """
        Sum what arrived into one account, in its own currency.

        :param account_id: account to total.
        :return: the total, ``0`` if nothing arrived.
        """
        query = select(func.coalesce(func.sum(Transfer.to_amount), 0)).where(
            Transfer.to_account_id == account_id
        )
        return (await self.session.exec(query)).one()

    async def sum_out(self, account_id: uuid.UUID) -> Decimal:
        """
        Sum what left one account, in its own currency.

        :param account_id: account to total.
        :return: the total, ``0`` if nothing left.
        """
        query = select(func.coalesce(func.sum(Transfer.amount), 0)).where(
            Transfer.from_account_id == account_id
        )
        return (await self.session.exec(query)).one()

    async def sum_to_savings_accounts(
        self,
        requester_id: uuid.UUID,
        owner_ids: set[uuid.UUID],
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Decimal:
        """
        Sum transfers landing in ``is_savings`` accounts.

        Same visibility rule as :meth:`list_for_range`.

        :param requester_id: user asking for the total.
        :param owner_ids: owners whose transfers are in scope.
        :param date_from: earliest ``transferred_at``, inclusive.
        :param date_to: latest ``transferred_at``, inclusive.
        :return: the total of ``to_amount``, ``0`` if nothing matched.
        """
        query = (
            select(func.coalesce(func.sum(Transfer.to_amount), 0))
            .join(Account, col(Account.id) == col(Transfer.to_account_id))
            .where(col(Account.is_savings).is_(True))
            .where(col(Transfer.user_id).in_(owner_ids))
            .where(
                or_(
                    Transfer.user_id == requester_id,
                    Transfer.visibility == Visibility.FAMILY,
                )
            )
        )
        if date_from is not None:
            query = query.where(col(Transfer.transferred_at) >= date_from)
        if date_to is not None:
            query = query.where(col(Transfer.transferred_at) <= date_to)
        return (await self.session.exec(query)).one()
