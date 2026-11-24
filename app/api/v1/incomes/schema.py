import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.sql.models.enums import Visibility


class IncomeRead(BaseModel):
    """Represents an income returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    category_id: int
    amount: Decimal
    description: str | None = None
    received_at: date
    visibility: Visibility
    planned_income_id: uuid.UUID | None = None
    recurring_occurrence_id: uuid.UUID | None = None


class IncomeCreate(BaseModel):
    """Represents an income-creation payload."""

    account_id: uuid.UUID
    category_id: int
    amount: Decimal
    received_at: date
    description: str | None = None
    visibility: Visibility = Visibility.PRIVATE


class IncomeUpdate(BaseModel):
    """Represents an income-update payload; unset fields are left as-is."""

    account_id: uuid.UUID | None = None
    category_id: int | None = None
    amount: Decimal | None = None
    received_at: date | None = None
    description: str | None = None
    visibility: Visibility | None = None
