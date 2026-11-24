from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.spent import Spent


class SpentDAO(BaseQuery[Spent]):
    """SQL queries for the spent table, via SQLModel."""

    _model = Spent
