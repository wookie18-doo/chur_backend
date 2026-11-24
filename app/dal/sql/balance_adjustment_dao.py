from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.account import BalanceAdjustment


class BalanceAdjustmentDAO(BaseQuery[BalanceAdjustment]):
    """SQL queries for the balance_adjustment table, via SQLModel."""

    _model = BalanceAdjustment
