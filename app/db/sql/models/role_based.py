import uuid

from sqlmodel import Field

from app.db.sql.base import Base


class Permission(Base, table=True):
    """A single permission that can be granted to a role."""

    __tablename__ = "permission"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200, unique=True)


class Role(Base, table=True):
    """A named group of permissions that can be assigned to users."""

    __tablename__ = "role"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200, unique=True)


class RolePermission(Base, table=True):
    """Associates a role with a permission it grants."""

    __tablename__ = "role_permission"

    role_id: int = Field(foreign_key="role.id", primary_key=True)
    permission_id: int = Field(foreign_key="permission.id", primary_key=True)


class UserRole(Base, table=True):
    """Associates a user with a role assigned to them."""

    __tablename__ = "user_role"

    user_id: uuid.UUID = Field(foreign_key="user.id", primary_key=True)
    role_id: int = Field(foreign_key="role.id", primary_key=True)


class UserPermission(Base, table=True):
    """Grants a permission directly to a user, bypassing roles."""

    __tablename__ = "user_permission"

    user_id: uuid.UUID = Field(foreign_key="user.id", primary_key=True)
    permission_id: int = Field(foreign_key="permission.id", primary_key=True)
