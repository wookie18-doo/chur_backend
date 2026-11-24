from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.account import Account


class AccountDAO(BaseQuery[Account]):
    """SQL queries for the account table, via SQLModel."""

    _model = Account
