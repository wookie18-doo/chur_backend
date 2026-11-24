import uuid

from pydantic import BaseModel, ConfigDict, model_validator

from app.db.sql.models.enums import FamilyRole
from app.db.sql.models.family import FamilyMember
from app.db.sql.models.users import User


class FamilyCreate(BaseModel):
    """Represents a family-creation payload."""

    name: str


class FamilyRead(BaseModel):
    """Represents a family returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class FamilyMemberRead(BaseModel):
    """Represents a family membership returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    family_id: uuid.UUID
    role: FamilyRole
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None

    @classmethod
    def build(cls, member: FamilyMember, user: User) -> "FamilyMemberRead":
        """
        Combine a membership with the member's user details.

        :param member: the membership row.
        :param user: the member's user.
        :return: the API representation.
        """
        return cls(
            user_id=member.user_id,
            family_id=member.family_id,
            role=member.role,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
        )


class FamilyWithMembers(FamilyRead):
    """Represents a family together with its members."""

    members: list[FamilyMemberRead]


class FamilyMemberAdd(BaseModel):
    """Represents a request to add a user, by id or email, to the family."""

    user_id: uuid.UUID | None = None
    email: str | None = None

    @model_validator(mode="after")
    def _require_one_identifier(self) -> "FamilyMemberAdd":
        if self.user_id is None and not self.email:
            msg = "Either user_id or email is required."
            raise ValueError(msg)
        return self


class FamilyUpdate(BaseModel):
    """Represents a family-rename payload."""

    name: str


class FamilyMemberRoleUpdate(BaseModel):
    """Represents a request to change a member's role."""

    role: FamilyRole
