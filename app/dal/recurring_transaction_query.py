"""
Router in front of the concrete recurring-transaction DAO.

``RecurringTransactionQuery`` inherits directly from the concrete
``RecurringTransactionDAO`` for whichever backend was chosen, so every
generic ``create``/``get``/``retrieve``/``update``/``delete`` operation
is already available on it as an inherited method, and it only adds the
domain-specific lookups ``RecurringTransactionService`` needs on top of
them.
"""

import uuid
from datetime import date

from sqlmodel import col, or_, select

from app.dal.sql.recurring_transaction_dao import RecurringTransactionDAO
from app.db.sql.models.enums import Visibility
from app.db.sql.models.recurring_transaction import RecurringTransaction


class RecurringTransactionQuery(RecurringTransactionDAO):
    """Everything ``RecurringTransactionService`` needs for recurring rules."""

    async def due(self, as_of: date) -> list[RecurringTransaction]:
        """
        Fetch every active rule whose next occurrence has arrived.

        :param as_of: the date to sweep as of.
        :return: due rules, earliest ``next_run_at`` first.
        """
        query = (
            select(RecurringTransaction)
            .where(col(RecurringTransaction.is_active).is_(True))
            .where(col(RecurringTransaction.next_run_at) <= as_of)
            .order_by(col(RecurringTransaction.next_run_at))
        )
        result = await self.session.exec(query)
        return list(result.all())

    async def list_visible(
        self, requester_id: uuid.UUID, owner_ids: set[uuid.UUID]
    ) -> list[RecurringTransaction]:
        """
        Fetch recurring rules visible to ``requester_id`` among ``owner_ids``.

        Same visibility rule as ``SpentQuery.list_for_range``.

        :param requester_id: user asking for the list.
        :param owner_ids: owners whose rules are in scope.
        :return: matching rules.
        """
        query = (
            select(RecurringTransaction)
            .where(col(RecurringTransaction.user_id).in_(owner_ids))
            .where(
                or_(
                    RecurringTransaction.user_id == requester_id,
                    RecurringTransaction.visibility == Visibility.FAMILY,
                )
            )
        )
        result = await self.session.exec(query)
        return list(result.all())
