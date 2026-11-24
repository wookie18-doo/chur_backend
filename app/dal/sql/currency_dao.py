from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.currency import Currency


class CurrencyDAO(BaseQuery[Currency]):
    """SQL queries for the currency table, via SQLModel."""

    _model = Currency
