"""Router in front of the concrete balance-adjustment DAO."""

import uuid
from decimal import Decimal

from sqlmodel import func, select

from app.dal.sql.balance_adjustment_dao import BalanceAdjustmentDAO
from app.db.sql.models.account import BalanceAdjustment


class BalanceAdjustmentQuery(BalanceAdjustmentDAO):
    """Everything ``AccountService`` needs for balance corrections."""

    async def sum_for_account(self, account_id: uuid.UUID) -> Decimal:
        """
        Sum every adjustment delta recorded for one account.

        :param account_id: account to total.
        :return: the total, ``0`` if there are none.
        """
        query = select(func.coalesce(func.sum(BalanceAdjustment.delta), 0)).where(
            BalanceAdjustment.account_id == account_id
        )
        return (await self.session.exec(query)).one()
