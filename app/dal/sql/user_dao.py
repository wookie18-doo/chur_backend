from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.users import User


class UserDAO(BaseQuery[User]):
    """SQL queries for the user table, via SQLModel."""

    _model = User
