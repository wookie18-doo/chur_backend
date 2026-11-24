import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.sql.models.enums import Visibility


class TransferRead(BaseModel):
    """Represents a transfer returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    amount: Decimal
    to_amount: Decimal
    description: str | None = None
    transferred_at: date
    visibility: Visibility


class TransferCreate(BaseModel):
    """Represents a transfer-creation payload."""

    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    amount: Decimal
    transferred_at: date
    to_amount: Decimal | None = None
    description: str | None = None
    visibility: Visibility = Visibility.PRIVATE


class TransferUpdate(BaseModel):
    """Represents a transfer-update payload; unset fields are left as-is."""

    from_account_id: uuid.UUID | None = None
    to_account_id: uuid.UUID | None = None
    amount: Decimal | None = None
    to_amount: Decimal | None = None
    transferred_at: date | None = None
    description: str | None = None
    visibility: Visibility | None = None
