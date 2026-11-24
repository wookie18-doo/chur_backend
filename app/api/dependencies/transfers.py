"""Wiring for the transfers subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.transfer_service import TransferService


def get_transfer_service(
    session: AsyncSession = Depends(get_db_session),
) -> TransferService:
    """
    Build a :class:`~app.services.transfer_service.TransferService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return TransferService(session)
