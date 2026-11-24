import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.sql.models.enums import Visibility


class SpentItemRead(BaseModel):
    """Represents a spent's line item returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: int | None = None
    name: str
    amount: Decimal
    quantity: str | None = None


class SpentItemCreate(BaseModel):
    """Represents a line-item creation payload."""

    name: str
    amount: Decimal
    category_id: int | None = None
    quantity: str | None = None


class SpentItemUpdate(BaseModel):
    """Represents a line-item update payload; unset fields are left as-is."""

    name: str | None = None
    amount: Decimal | None = None
    category_id: int | None = None
    quantity: str | None = None


class SpentRead(BaseModel):
    """Represents a spent returned from a list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    category_id: int
    amount: Decimal
    description: str | None = None
    spent_at: date
    visibility: Visibility
    item_count: int = 0
    wishlist_item_id: uuid.UUID | None = None
    recurring_occurrence_id: uuid.UUID | None = None


class SpentDetailRead(SpentRead):
    """Represents a spent returned from the detail endpoint."""

    items: list[SpentItemRead]
    items_total: Decimal | None = None


class SpentCreate(BaseModel):
    """Represents a spent-creation payload."""

    account_id: uuid.UUID
    category_id: int
    amount: Decimal
    spent_at: date
    description: str | None = None
    visibility: Visibility = Visibility.PRIVATE


class SpentUpdate(BaseModel):
    """Represents a spent-update payload; unset fields are left as-is."""

    account_id: uuid.UUID | None = None
    category_id: int | None = None
    amount: Decimal | None = None
    spent_at: date | None = None
    description: str | None = None
    visibility: Visibility | None = None
