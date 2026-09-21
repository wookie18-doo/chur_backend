import uuid
from datetime import datetime

from sqlmodel import Field

from app.db.sql.base import Base


class User(Base, table=True):
    """Represents a user entity."""

    __tablename__ = "user"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(max_length=320, unique=True, index=True)
    hashed_password: str = Field(max_length=1024)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    otp_hash: str | None = Field(default=None, max_length=1024)
    otp_expires_at: datetime | None = Field(default=None)
    phone: str | None = Field(default=None, max_length=32, unique=True)
    username: str | None = Field(default=None, max_length=150, unique=True)
    first_name: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, max_length=150)
