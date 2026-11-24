from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.currency import ExchangeRate


class ExchangeRateDAO(BaseQuery[ExchangeRate]):
    """SQL queries for the exchange_rate table, via SQLModel."""

    _model = ExchangeRate
