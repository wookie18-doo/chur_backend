from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.planned_income import PlannedIncome


class PlannedIncomeDAO(BaseQuery[PlannedIncome]):
    """SQL queries for the planned_income table, via SQLModel."""

    _model = PlannedIncome
