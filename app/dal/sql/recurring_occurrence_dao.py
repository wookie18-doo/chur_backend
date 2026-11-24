from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.recurring_transaction import RecurringOccurrence


class RecurringOccurrenceDAO(BaseQuery[RecurringOccurrence]):
    """SQL queries for the recurring_occurrence table, via SQLModel."""

    _model = RecurringOccurrence
