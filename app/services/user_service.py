import uuid
from datetime import UTC, datetime, timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from app.config.settings import settings
from app.dal.user_query import UserQuery
from app.db.sql.models.users import User
from app.services.auth_service import (
    InvalidTokenError,
    create_token,
    decode_token,
    generate_otp_code,
    hash_secret,
    verify_secret,
)
from app.services.email_sender import EmailReason, EmailSender


class InvalidCredentialsError(Exception):
    """Raised when an email/password pair doesn't match a user."""


class InvalidOtpError(Exception):
    """Raised when an OTP code is missing, expired, or doesn't match."""


class UserService:
    """
    Business logic for registration, authentication, and account recovery.

    Builds its own :class:`~app.dal.user_query.UserQuery` from the db
    session/connection it's given -- callers never construct a query object
    themselves. Also depends on
    :class:`~app.services.email_sender.EmailSender` for delivering
    verification/reset/OTP emails. Neither hashing nor JWT handling happens
    here directly -- that's :mod:`app.services.auth_service`.
    """

    def __init__(self, session: AsyncSession, email_sender: EmailSender) -> None:
        self.dao = UserQuery(session)
        self.email_sender = email_sender

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """
        Fetch a user by primary key, e.g. to resolve a request's access token.

        :param user_id: user id.
        :return: the user, or ``None`` if it doesn't exist.
        """
        return await self.dao.get_by_id(user_id)

    async def register(
        self,
        email: str,
        password: str,
        *,
        phone: str | None = None,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        """
        Create a new user and kick off email verification.

        :param email: user email.
        :param password: plaintext password to hash and store.
        :param phone: user phone number.
        :param username: user handle.
        :param first_name: user first name.
        :param last_name: user last name.
        :return: the created user.
        """
        user = await self.dao.create(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hash_secret(password),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            phone=phone,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        token = create_token(
            user.id, "verify", settings.users_verification_token_lifetime_seconds
        )
        await self.email_sender.send(
            EmailReason.VERIFY_EMAIL, user.email, {"token": token}
        )
        return user

    async def authenticate(self, email: str, password: str) -> User:
        """
        Check credentials and return the matching active user.

        :param email: claimed email.
        :param password: claimed plaintext password.
        :raises InvalidCredentialsError: if the credentials don't match an
            active user.
        :return: the authenticated user.
        """
        user = await self.dao.get_by_email(email)
        if user is None or not verify_secret(password, user.hashed_password):
            raise InvalidCredentialsError
        if not user.is_active:
            raise InvalidCredentialsError
        return user

    def issue_access_token(self, user: User) -> str:
        """
        Issue an access token for an already-authenticated user.

        :param user: the user to issue a token for.
        :return: encoded access token.
        """
        return create_token(
            user.id, "access", settings.users_access_token_lifetime_seconds
        )

    async def request_password_reset(self, email: str) -> None:
        """
        Send a password-reset token, if ``email`` belongs to a user.

        Silently does nothing for unknown emails, so callers can't use this
        to enumerate registered accounts.

        :param email: email to send the reset token to.
        """
        user = await self.dao.get_by_email(email)
        if user is None:
            return
        token = create_token(
            user.id, "reset", settings.users_reset_password_token_lifetime_seconds
        )
        await self.email_sender.send(
            EmailReason.RESET_PASSWORD, user.email, {"token": token}
        )

    async def reset_password(self, token: str, new_password: str) -> None:
        """
        Consume a password-reset token and set a new password.

        :param token: reset token issued by :meth:`request_password_reset`.
        :param new_password: new plaintext password to hash and store.
        :raises app.services.auth_service.InvalidTokenError: if the token is
            invalid, expired, or the user no longer exists.
        """
        user_id = decode_token(token, expected_type="reset")
        user = await self.dao.get_by_id(user_id)
        if user is None:
            raise InvalidTokenError
        await self.dao.update_password(user, hash_secret(new_password))

    async def verify_email(self, token: str) -> None:
        """
        Consume an email-verification token.

        :param token: verification token issued during :meth:`register`.
        :raises app.services.auth_service.InvalidTokenError: if the token is
            invalid, expired, or the user no longer exists.
        """
        user_id = decode_token(token, expected_type="verify")
        user = await self.dao.get_by_id(user_id)
        if user is None:
            raise InvalidTokenError
        await self.dao.mark_verified(user)

    async def send_otp(self, email: str) -> None:
        """
        Generate and send a one-time-password, if ``email`` belongs to a user.

        Silently does nothing for unknown emails, so callers can't use this
        to enumerate registered accounts.

        :param email: email to send the OTP to.
        """
        user = await self.dao.get_by_email(email)
        if user is None:
            return
        code = generate_otp_code()
        expires_at = datetime.now(UTC) + timedelta(
            seconds=settings.users_otp_lifetime_seconds
        )
        await self.dao.set_otp(user, hash_secret(code), expires_at)
        await self.email_sender.send(EmailReason.OTP, user.email, {"code": code})

    async def verify_otp(self, email: str, code: str) -> User:
        """
        Consume a pending OTP code and return the matching user.

        :param email: email the OTP was requested for.
        :param code: OTP code to check.
        :raises InvalidOtpError: if there's no pending OTP, it expired, or
            ``code`` doesn't match.
        :return: the user the OTP belongs to.
        """
        user = await self.dao.get_by_email(email)
        if user is None:
            raise InvalidOtpError

        pending = await self.dao.get_otp(user)
        if pending is None:
            raise InvalidOtpError
        otp_hash, expires_at = pending
        if expires_at.tzinfo is None:
            # Some DB drivers (e.g. SQLite) drop tzinfo on round-trip; the
            # value was always stored as UTC, so treat a naive read as UTC.
            expires_at = expires_at.replace(tzinfo=UTC)
        if datetime.now(UTC) > expires_at or not verify_secret(code, otp_hash):
            raise InvalidOtpError

        await self.dao.clear_otp(user)
        return user
