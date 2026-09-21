"""
Password hashing and JWT issuing/verification.

This is the only place that touches ``bcrypt``/``jwt`` directly. Everything
else -- registration, login, password reset, email verification -- goes
through these functions so there is a single spot to change the hashing
scheme or token format.
"""

import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config.settings import settings

ALGORITHM = "HS256"
OTP_ALPHABET = string.digits


class InvalidTokenError(Exception):
    """Raised when a token is missing, malformed, expired, or of the wrong type."""


def hash_secret(secret: str) -> str:
    """
    Hash a plaintext secret (a password or an OTP code) for storage.

    :param secret: plaintext secret.
    :return: bcrypt hash, safe to store.
    """
    return bcrypt.hashpw(secret.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_secret(secret: str, hashed_secret: str) -> bool:
    """
    Check a plaintext secret against a stored hash.

    :param secret: plaintext secret to check.
    :param hashed_secret: hash to check it against.
    :return: whether they match.
    """
    return bcrypt.checkpw(secret.encode("utf-8"), hashed_secret.encode("utf-8"))


def generate_otp_code(length: int = 6) -> str:
    """
    Generate a random numeric one-time-password code.

    Uses :mod:`secrets`, not :mod:`random` -- this needs to be
    unguessable, not just look random.

    :param length: how many digits to generate.
    :return: the OTP code, as a zero-padded numeric string.
    """
    return "".join(secrets.choice(OTP_ALPHABET) for _ in range(length))


def create_token(user_id: uuid.UUID, token_type: str, lifetime_seconds: int) -> str:
    """
    Issue a signed JWT identifying ``user_id`` for a specific purpose.

    ``token_type`` (e.g. ``"access"``, ``"reset"``, ``"verify"``) is embedded
    in the token and checked on decode, so e.g. a password-reset token can't
    be replayed as an access token.

    :param user_id: subject of the token.
    :param token_type: purpose of the token.
    :param lifetime_seconds: seconds until the token expires.
    :return: encoded JWT.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(seconds=lifetime_seconds),
    }
    return jwt.encode(payload, settings.users_secret, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str) -> uuid.UUID:
    """
    Decode a token issued by :func:`create_token` and check its purpose.

    :param token: encoded JWT.
    :param expected_type: the ``token_type`` the caller requires.
    :return: the user id embedded in the token.
    :raises InvalidTokenError: if the token is invalid, expired, or of the
        wrong type.
    """
    try:
        payload = jwt.decode(token, settings.users_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError from exc
    if payload.get("type") != expected_type:
        raise InvalidTokenError
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError from exc
