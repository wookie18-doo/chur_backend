from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.category import Category


class CategoryDAO(BaseQuery[Category]):
    """SQL queries for the category table, via SQLModel."""

    _model = Category
