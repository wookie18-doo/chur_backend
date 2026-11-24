import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.sql.models.enums import (
    CategoryKind,
    PlanStatus,
    RecurrenceFrequency,
    Visibility,
)


class RecurringTransactionRead(BaseModel):
    """Represents a recurring transaction rule returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    kind: CategoryKind
    category_id: int
    amount: Decimal
    description: str | None = None
    visibility: Visibility
    frequency: RecurrenceFrequency
    interval: int
    day_of_month: int | None = None
    weekday: int | None = None
    start_date: date
    end_date: date | None = None
    next_run_at: date
    last_generated_at: date | None = None
    is_active: bool


class RecurringTransactionCreate(BaseModel):
    """Represents a recurring-transaction creation payload."""

    account_id: uuid.UUID
    kind: CategoryKind
    category_id: int
    amount: Decimal
    frequency: RecurrenceFrequency
    start_date: date
    interval: int = 1
    day_of_month: int | None = None
    weekday: int | None = None
    end_date: date | None = None
    description: str | None = None
    visibility: Visibility = Visibility.PRIVATE


class RecurringTransactionUpdate(BaseModel):
    """Represents a recurring-transaction update payload; unset fields stay as-is."""

    account_id: uuid.UUID | None = None
    kind: CategoryKind | None = None
    category_id: int | None = None
    amount: Decimal | None = None
    frequency: RecurrenceFrequency | None = None
    interval: int | None = None
    day_of_month: int | None = None
    weekday: int | None = None
    end_date: date | None = None
    description: str | None = None
    visibility: Visibility | None = None


class RecurringOccurrenceRead(BaseModel):
    """Represents a recurring occurrence returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recurring_transaction_id: uuid.UUID
    due_date: date
    status: PlanStatus
    completed_at: date | None = None
    spent_id: uuid.UUID | None = None
    income_id: uuid.UUID | None = None


class CompleteOccurrence(BaseModel):
    """
    Represents a request to confirm an occurrence.

    Either link an existing spent/income, or leave both unset to post a
    new one, optionally overriding ``amount``/``account_id``/``category_id``.
    """

    completed_at: date | None = None
    existing_spent_id: uuid.UUID | None = None
    existing_income_id: uuid.UUID | None = None
    amount: Decimal | None = None
    account_id: uuid.UUID | None = None
    category_id: int | None = None


class OccurrenceCompletedAtUpdate(BaseModel):
    """Represents a request to edit an occurrence's completion date."""

    completed_at: date
