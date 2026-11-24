"""
Router in front of the concrete planned-income DAO.

``PlannedIncomeQuery`` inherits directly from the concrete
``PlannedIncomeDAO`` for whichever backend was chosen, so every generic
``create``/``get``/``retrieve``/``update``/``delete`` operation is
already available on it as an inherited method, and it only adds the
domain-specific lookups ``PlannedIncomeService`` needs on top of them.
"""

import uuid

from sqlmodel import col, or_, select

from app.dal.sql.planned_income_dao import PlannedIncomeDAO
from app.db.sql.models.enums import Visibility
from app.db.sql.models.planned_income import PlannedIncome


class PlannedIncomeQuery(PlannedIncomeDAO):
    """Everything ``PlannedIncomeService`` needs to read/write planned incomes."""

    async def list_visible(
        self, requester_id: uuid.UUID, owner_ids: set[uuid.UUID]
    ) -> list[PlannedIncome]:
        """
        Fetch planned incomes visible to ``requester_id`` among ``owner_ids``.

        Same visibility rule as ``SpentQuery.list_for_range``.

        :param requester_id: user asking for the list.
        :param owner_ids: owners whose planned incomes are in scope.
        :return: matching planned incomes.
        """
        query = (
            select(PlannedIncome)
            .where(col(PlannedIncome.user_id).in_(owner_ids))
            .where(
                or_(
                    PlannedIncome.user_id == requester_id,
                    PlannedIncome.visibility == Visibility.FAMILY,
                )
            )
        )
        result = await self.session.exec(query)
        return list(result.all())
