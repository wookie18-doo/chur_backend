from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.income import Income


class IncomeDAO(BaseQuery[Income]):
    """SQL queries for the income table, via SQLModel."""

    _model = Income
