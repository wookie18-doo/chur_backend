import uuid

from pydantic import BaseModel, ConfigDict

from app.db.sql.models.enums import CategoryColor, CategoryKind


class CategoryRead(BaseModel):
    """Represents a category returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: CategoryKind
    color: CategoryColor | None = None
    owner_id: uuid.UUID | None = None


class CategoryCreate(BaseModel):
    """Represents a custom-category creation payload."""

    name: str
    kind: CategoryKind
    color: CategoryColor | None = None


class CategoryUpdate(BaseModel):
    """Represents a custom-category update; omitted fields stay unchanged."""

    name: str | None = None
    color: CategoryColor | None = None
