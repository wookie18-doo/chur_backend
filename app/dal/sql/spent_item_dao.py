from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.spent import SpentItem


class SpentItemDAO(BaseQuery[SpentItem]):
    """SQL queries for the spent_item table, via SQLModel."""

    _model = SpentItem
