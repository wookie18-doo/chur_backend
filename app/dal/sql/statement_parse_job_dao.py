from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.statement_parse_job import StatementParseJob


class StatementParseJobDAO(BaseQuery[StatementParseJob]):
    """SQL queries for the statement_parse_job table, via SQLModel."""

    _model = StatementParseJob
