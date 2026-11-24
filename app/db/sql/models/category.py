import uuid

from sqlmodel import Field

from app.db.sql.base import Base
from app.db.sql.models.enums import CategoryColor, CategoryKind


class Category(Base, table=True):
    """
    A category a spent or income can be filed under.

    ``owner_id = NULL`` marks a built-in category, visible to and usable
    by everyone; a set ``owner_id`` marks a user's own custom category,
    usable only by them.
    """

    __tablename__ = "category"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    kind: CategoryKind
    owner_id: uuid.UUID | None = Field(default=None, foreign_key="user.id")
    color: CategoryColor | None = Field(default=None)
