"""
Wiring for the hand-rolled auth/user subsystem.

Password hashing and JWT logic live in ``app.services.auth_service``.
``UserService`` builds its own ``app.dal.user_query.UserQuery`` from a db
session/connection -- this module never constructs a DAL object itself, it
just hands ``UserService`` whatever session/connection the chosen backend
needs, plus an ``app.services.email_sender.EmailSender``. Resolving who's
making the request is not this module's job: ``app.api.middlewares.auth``
does that for every request, and ``app.api.dependencies.auth.require_auth``
reads the result off ``request.state.user``.
"""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.email_sender import EmailSender, NoopEmailSender
from app.services.user_service import UserService


def get_email_sender() -> EmailSender:
    """
    Build the :class:`~app.services.email_sender.EmailSender` implementation.

    Swap ``NoopEmailSender`` for a real provider here once you have one --
    ``UserService`` only depends on the ``EmailSender`` protocol.

    :return: email sender instance.
    """
    return NoopEmailSender()


def get_user_service(
    session: AsyncSession = Depends(get_db_session),
    email_sender: EmailSender = Depends(get_email_sender),
) -> UserService:
    """
    Build a :class:`~app.services.user_service.UserService` for the current request.

    :param session: asynchronous database session.
    :param email_sender: email delivery.
    :return: service instance.
    """
    return UserService(session, email_sender)
