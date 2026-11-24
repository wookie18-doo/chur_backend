"""
Router in front of the concrete wishlist DAO.

``WishlistQuery`` inherits directly from the concrete ``WishlistDAO`` for
whichever backend was chosen, so every generic ``create``/``get``/
``retrieve``/``update``/``delete`` operation is already available on it
as an inherited method, and it only adds the domain-specific lookups
``WishlistService`` needs on top of them.
"""

import uuid

from sqlmodel import col, or_, select

from app.dal.sql.wishlist_dao import WishlistDAO
from app.db.sql.models.enums import Visibility
from app.db.sql.models.wishlist import Wishlist


class WishlistQuery(WishlistDAO):
    """Everything ``WishlistService`` needs to read and write wishlist data."""

    async def list_visible(
        self, requester_id: uuid.UUID, owner_ids: set[uuid.UUID]
    ) -> list[Wishlist]:
        """
        Fetch wishlists visible to ``requester_id`` among ``owner_ids``.

        Same visibility rule as ``SpentQuery.list_for_range``: a row
        passes when its owner is ``requester_id`` (any visibility) or
        the owner is one of ``owner_ids`` and the row is
        ``Visibility.FAMILY``.

        :param requester_id: user asking for the list.
        :param owner_ids: owners whose wishlists are in scope.
        :return: matching wishlists.
        """
        query = (
            select(Wishlist)
            .where(col(Wishlist.user_id).in_(owner_ids))
            .where(
                or_(
                    Wishlist.user_id == requester_id,
                    Wishlist.visibility == Visibility.FAMILY,
                )
            )
        )
        result = await self.session.exec(query)
        return list(result.all())
