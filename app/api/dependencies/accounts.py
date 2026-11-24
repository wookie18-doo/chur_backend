"""Wiring for the accounts subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.account_service import AccountService


def get_account_service(
    session: AsyncSession = Depends(get_db_session),
) -> AccountService:
    """
    Build a :class:`~app.services.account_service.AccountService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return AccountService(session)
