"""Wiring for the wishlists subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.wishlist_service import WishlistService


def get_wishlist_service(
    session: AsyncSession = Depends(get_db_session),
) -> WishlistService:
    """
    Build a :class:`~app.services.wishlist_service.WishlistService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return WishlistService(session)
