from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.statement_source import StatementSourceRecord


class StatementSourceDAO(BaseQuery[StatementSourceRecord]):
    """SQL queries for the statement_source table, via SQLModel."""

    _model = StatementSourceRecord
