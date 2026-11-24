"""
Router in front of the concrete recurring-occurrence DAO.

Adds the domain-specific lookups ``RecurringTransactionService`` needs on
top of the generic CRUD operations inherited from the DAO.
"""

import uuid

from sqlmodel import col, or_, select

from app.dal.sql.recurring_occurrence_dao import RecurringOccurrenceDAO
from app.db.sql.models.enums import PlanStatus, Visibility
from app.db.sql.models.recurring_transaction import (
    RecurringOccurrence,
    RecurringTransaction,
)


class RecurringOccurrenceQuery(RecurringOccurrenceDAO):
    """Everything ``RecurringTransactionService`` needs for occurrences."""

    async def list_visible(
        self,
        requester_id: uuid.UUID,
        owner_ids: set[uuid.UUID],
        *,
        status: PlanStatus | None = None,
    ) -> list[RecurringOccurrence]:
        """
        Fetch occurrences visible to ``requester_id`` among ``owner_ids``.

        Occurrences have no visibility of their own -- they inherit the
        parent rule's, so this joins through ``recurring_transaction``.

        :param requester_id: user asking for the list.
        :param owner_ids: owners whose occurrences are in scope.
        :param status: restrict to one lifecycle state.
        :return: matching occurrences, earliest due date first.
        """
        query = (
            select(RecurringOccurrence)
            .join(
                RecurringTransaction,
                col(RecurringTransaction.id)
                == col(RecurringOccurrence.recurring_transaction_id),
            )
            .where(col(RecurringTransaction.user_id).in_(owner_ids))
            .where(
                or_(
                    RecurringTransaction.user_id == requester_id,
                    RecurringTransaction.visibility == Visibility.FAMILY,
                )
            )
            .order_by(col(RecurringOccurrence.due_date))
        )
        if status is not None:
            query = query.where(RecurringOccurrence.status == status)
        result = await self.session.exec(query)
        return list(result.all())
