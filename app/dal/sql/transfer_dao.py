from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.transfer import Transfer


class TransferDAO(BaseQuery[Transfer]):
    """SQL queries for the transfer table, via SQLModel."""

    _model = Transfer
