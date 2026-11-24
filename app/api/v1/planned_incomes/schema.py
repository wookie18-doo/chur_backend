import uuid
from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from app.db.sql.models.enums import PlanStatus, RecurrenceFrequency, Visibility


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


class PlannedIncomeRead(BaseModel):
    """Represents a planned income returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    category_id: int
    name: str
    amount: Decimal
    date_from: date | None = None
    date_to: date | None = None
    frequency: RecurrenceFrequency | None = None
    repeat_until: date | None = None
    visibility: Visibility
    status: PlanStatus
    realised_income_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def repeat(self) -> bool:
        """Whether realising rolls this item forward to its next window."""
        return self.frequency is not None


class PlannedIncomeCreate(RepeatMixin):
    """Represents a planned-income creation payload."""

    name: str
    category_id: int
    amount: Decimal
    date_from: date | None = None
    date_to: date | None = None
    visibility: Visibility = Visibility.PRIVATE
    account_id: uuid.UUID | None = None


class PlannedIncomeUpdate(RepeatMixin):
    """Represents a planned-income update payload; unset fields are left as-is."""

    name: str | None = None
    category_id: int | None = None
    amount: Decimal | None = None
    date_from: date | None = None
    date_to: date | None = None
    visibility: Visibility | None = None
    account_id: uuid.UUID | None = None


class PlannedIncomeCandidateRead(BaseModel):
    """Represents a candidate income for realising a planned income."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    category_id: int
    amount: Decimal
    received_at: date


class PlannedIncomeRealise(BaseModel):
    """
    Represents a request to mark a planned income as received.

    Either set ``existing_income_id`` (merge into an already-recorded
    income) or leave it unset and provide at least ``account_id`` (create
    a new income) -- see ``PlannedIncomeService.realise``.
    """

    existing_income_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    category_id: int | None = None
    amount: Decimal | None = None
    received_at: date | None = None
    visibility: Visibility | None = None
