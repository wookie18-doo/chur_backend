import uuid
from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from app.db.sql.models.enums import PlanStatus, RecurrenceFrequency, Visibility


class WishlistRead(BaseModel):
    """Represents a wishlist returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    visibility: Visibility


class WishlistCreate(BaseModel):
    """Represents a wishlist-creation payload."""

    name: str
    description: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    visibility: Visibility = Visibility.PRIVATE


class WishlistUpdate(BaseModel):
    """Represents a wishlist-update payload; unset fields are left as-is."""

    name: str | None = None
    description: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    visibility: Visibility | None = None


class RepeatMixin(BaseModel):
    """Optional ``repeat`` flag with its ``frequency``, shared by plan payloads."""

    repeat: bool | None = None
    frequency: RecurrenceFrequency | None = None
    repeat_until: date | None = None

    @model_validator(mode="after")
    def _frequency_matches_flag(self) -> Self:
        if self.repeat and self.frequency is None:
            raise ValueError("frequency is required when repeat is true")
        if not self.repeat and self.frequency is not None:
            raise ValueError("frequency needs repeat to be true")
        return self


class WishlistItemRead(BaseModel):
    """Represents a wishlist item returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    wishlist_id: uuid.UUID
    category_id: int
    name: str
    amount: Decimal
    planned_date: date | None = None
    planned_date_to: date | None = None
    frequency: RecurrenceFrequency | None = None
    repeat_until: date | None = None
    visibility: Visibility | None = None
    status: PlanStatus
    realised_spent_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def repeat(self) -> bool:
        """Whether realising rolls this item forward to its next window."""
        return self.frequency is not None


class WishlistItemCreate(RepeatMixin):
    """Represents a wishlist-item creation payload."""

    category_id: int
    name: str
    amount: Decimal
    planned_date: date | None = None
    planned_date_to: date | None = None
    visibility: Visibility | None = None
    account_id: uuid.UUID | None = None


class WishlistItemUpdate(RepeatMixin):
    """Represents a wishlist-item update payload; unset fields are left as-is."""

    category_id: int | None = None
    name: str | None = None
    amount: Decimal | None = None
    planned_date: date | None = None
    planned_date_to: date | None = None
    visibility: Visibility | None = None
    account_id: uuid.UUID | None = None


class WishlistItemTransfer(BaseModel):
    """Represents a request to move an item to another wishlist."""

    target_wishlist_id: uuid.UUID


class WishlistCandidateSpentRead(BaseModel):
    """Represents a candidate spent for realising a wishlist item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    category_id: int
    amount: Decimal
    spent_at: date


class WishlistItemRealise(BaseModel):
    """
    Represents a request to mark a wishlist item as bought.

    Either set ``existing_spent_id`` (merge into an already-recorded
    spent) or leave it unset and provide at least ``account_id`` (create
    a new spent) -- see ``WishlistService.realise_item``.
    """

    existing_spent_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    category_id: int | None = None
    amount: Decimal | None = None
    spent_at: date | None = None
    visibility: Visibility | None = None
