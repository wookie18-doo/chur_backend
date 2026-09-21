"""
Router in front of the concrete user DAO.

``UserQuery`` inherits directly from the concrete ``UserDAO`` for whichever
backend was chosen (``app.dal.sql.user_dao.UserDAO`` for SQL databases, or a
future ``app.dal.nosql.user_dao.UserDAO`` for MongoDB/Motor) -- so every
generic ``create``/``get``/``retrieve``/``update``/``delete`` operation is
already available on it as an inherited method, and it only adds the
domain-specific lookups ``UserService`` needs on top of them.
``UserService`` is written entirely against this class and builds it itself
from a db session/connection -- swapping backends means swapping which
``UserDAO`` it inherits from, not touching ``UserService``.
"""

import uuid
from datetime import datetime

from app.dal.sql.user_dao import UserDAO
from app.db.sql.models.users import User


class UserQuery(UserDAO):
    """Everything ``UserService`` needs to read and write user data."""

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """
        Fetch a user by primary key.

        :param user_id: user id.
        :return: the user, or ``None`` if it doesn't exist.
        """
        return await self.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        """
        Fetch a user by email.

        :param email: user email.
        :return: the user, or ``None`` if it doesn't exist.
        """
        matches = await self.retrieve(limit=1, email=email)
        return matches[0] if matches else None

    async def update_password(self, user: User, hashed_password: str) -> None:
        """
        Overwrite a user's stored password hash.

        :param user: user to update.
        :param hashed_password: already-hashed new password.
        """
        await self.update(user.id, hashed_password=hashed_password)

    async def mark_verified(self, user: User) -> None:
        """
        Flag a user's email as verified.

        :param user: user to update.
        """
        await self.update(user.id, is_verified=True)

    async def set_otp(self, user: User, otp_hash: str, expires_at: datetime) -> None:
        """
        Store a one-time-password hash and its expiry for a user.

        Overwrites any previously pending OTP.

        :param user: user to update.
        :param otp_hash: hash of the OTP code, not the code itself.
        :param expires_at: when the OTP stops being valid.
        """
        await self.update(user.id, otp_hash=otp_hash, otp_expires_at=expires_at)

    async def get_otp(self, user: User) -> tuple[str, datetime] | None:
        """
        Fetch the pending OTP hash and expiry for a user, if any.

        :param user: user to look up.
        :return: ``(otp_hash, expires_at)``, or ``None`` if there's no
            pending OTP.
        """
        if user.otp_hash is None or user.otp_expires_at is None:
            return None
        return user.otp_hash, user.otp_expires_at

    async def clear_otp(self, user: User) -> None:
        """
        Remove a user's pending OTP, if any.

        :param user: user to update.
        """
        await self.update(user.id, otp_hash=None, otp_expires_at=None)
