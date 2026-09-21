import uuid

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRead(BaseModel):
    """Represents a user returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    is_superuser: bool
    is_verified: bool
    phone: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class UserCreate(BaseModel):
    """Represents a registration payload."""

    email: EmailStr
    password: str
    phone: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class LoginRequest(BaseModel):
    """Represents a login payload."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Represents an issued access token."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105


class ForgotPasswordRequest(BaseModel):
    """Represents a password-reset request payload."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Represents a password-reset confirmation payload."""

    token: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    """Represents an email-verification payload."""

    token: str


class RequestOtpRequest(BaseModel):
    """Represents a one-time-password request payload."""

    email: EmailStr


class VerifyOtpRequest(BaseModel):
    """Represents a one-time-password confirmation payload."""

    email: EmailStr
    code: str
