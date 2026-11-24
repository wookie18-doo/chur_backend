from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.wishlist import Wishlist


class WishlistDAO(BaseQuery[Wishlist]):
    """SQL queries for the wishlist table, via SQLModel."""

    _model = Wishlist
