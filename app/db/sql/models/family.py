import uuid

from sqlmodel import Field

from app.db.sql.base import Base
from app.db.sql.models.enums import FamilyRole


class Family(Base, table=True):
    """A group of users who can share visibility of their own records."""

    __tablename__ = "family"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=200)


class FamilyMember(Base, table=True):
    """
    A user's membership in a family.

    ``user_id`` is the primary key -- a user belongs to at most one family
    at a time, which keeps the visibility rule (``app.services.
    visibility_service``) a single lookup instead of a set union.
    """

    __tablename__ = "family_member"

    user_id: uuid.UUID = Field(foreign_key="user.id", primary_key=True)
    family_id: uuid.UUID = Field(foreign_key="family.id", index=True)
    role: FamilyRole = Field(default=FamilyRole.MEMBER)
