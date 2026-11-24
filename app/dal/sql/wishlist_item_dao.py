from app.dal.sql.base_query import BaseQuery
from app.db.sql.models.wishlist import WishlistItem


class WishlistItemDAO(BaseQuery[WishlistItem]):
    """SQL queries for the wishlist_item table, via SQLModel."""

    _model = WishlistItem
