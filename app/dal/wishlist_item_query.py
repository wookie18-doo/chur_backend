"""
Router in front of the concrete wishlist-item DAO.

``WishlistItemQuery`` inherits directly from the concrete
``WishlistItemDAO`` for whichever backend was chosen, so every generic
``create``/``get``/``retrieve``/``update``/``delete`` operation is
already available on it as an inherited method, and it only adds the
domain-specific lookups ``WishlistService`` needs on top of them.
"""

import uuid

from app.dal.sql.wishlist_item_dao import WishlistItemDAO
from app.db.sql.models.wishlist import WishlistItem


class WishlistItemQuery(WishlistItemDAO):
    """Everything ``WishlistService`` needs to read and write wishlist items."""

    async def list_by_wishlist(self, wishlist_id: uuid.UUID) -> list[WishlistItem]:
        """
        Fetch every item on a wishlist.

        :param wishlist_id: parent wishlist.
        :return: its items.
        """
        return await self.retrieve(wishlist_id=wishlist_id)
