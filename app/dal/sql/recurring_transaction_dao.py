from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.recurring_transaction import RecurringTransaction


class RecurringTransactionDAO(BaseQuery[RecurringTransaction]):
    """SQL queries for the recurring_transaction table, via SQLModel."""

    _model = RecurringTransaction
