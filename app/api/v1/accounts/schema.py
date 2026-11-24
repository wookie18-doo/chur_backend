import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.sql.models.enums import AccountKind


class AccountRead(BaseModel):
    """Represents an account returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: AccountKind
    currency: str
    source: str | None = None
    is_active: bool
    opening_balance: Decimal | None = None
    parent_account_id: uuid.UUID | None = None
    is_savings: bool = False


class AccountCreate(BaseModel):
    """Represents an account-creation payload."""

    name: str
    kind: AccountKind
    currency: str
    source: str | None = None
    opening_balance: Decimal | None = None
    parent_account_id: uuid.UUID | None = None
    is_savings: bool = False


class AccountUpdate(BaseModel):
    """Represents an account-update payload; unset fields are left as-is."""

    name: str | None = None
    kind: AccountKind | None = None
    currency: str | None = None
    source: str | None = None
    opening_balance: Decimal | None = None
    parent_account_id: uuid.UUID | None = None
    is_savings: bool | None = None


class BalanceRead(BaseModel):
    """Represents an account's current balance."""

    current_balance: Decimal


class BalanceSet(BaseModel):
    """Represents a request to make an account's balance equal a target."""

    target_balance: Decimal
    as_of: date | None = None
    reason: str | None = None


class BalanceAdjustmentRead(BaseModel):
    """Represents a balance adjustment returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    delta: Decimal
    reason: str | None = None
    adjusted_at: date
