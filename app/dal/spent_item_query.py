"""
Router in front of the concrete spent-item DAO.

``SpentItemQuery`` inherits directly from the concrete ``SpentItemDAO``
for whichever backend was chosen, so every generic ``create``/``get``/
``retrieve``/``update``/``delete`` operation is already available on it
as an inherited method, and it only adds the domain-specific lookups
``SpentService`` needs on top of them.
"""

import uuid
from decimal import Decimal

from sqlmodel import col, func, select

from app.dal.sql.spent_item_dao import SpentItemDAO
from app.db.sql.models.spent import SpentItem


class SpentItemQuery(SpentItemDAO):
    """Everything ``SpentService`` needs to read and write spent-item data."""

    async def list_by_spent(self, spent_id: uuid.UUID) -> list[SpentItem]:
        """
        Fetch every line item attached to a spent.

        :param spent_id: parent spent.
        :return: its line items.
        """
        return await self.retrieve(spent_id=spent_id)

    async def count_by_spents(self, spent_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """
        Count line items per spent, for a batch of spents at once.

        Used by the list endpoint to avoid one query per row just to show
        each spent's ``item_count``.

        :param spent_ids: spents to count items for.
        :return: mapping of spent id to its item count; spents with no
            items are simply absent, not mapped to ``0``.
        """
        if not spent_ids:
            return {}
        query = (
            select(SpentItem.spent_id, func.count())
            .where(col(SpentItem.spent_id).in_(spent_ids))
            .group_by(col(SpentItem.spent_id))
        )
        result = await self.session.exec(query)
        return dict(result.all())

    async def sum_by_spent(self, spent_id: uuid.UUID) -> Decimal | None:
        """
        Sum a spent's line items.

        :param spent_id: parent spent.
        :return: the total, or ``None`` if it has no line items yet --
            distinct from a total of ``0``, which means it has items that
            happen to sum to zero (e.g. a fully discounted line).
        """
        query = select(func.sum(SpentItem.amount)).where(SpentItem.spent_id == spent_id)
        result = await self.session.exec(query)
        return result.one()
