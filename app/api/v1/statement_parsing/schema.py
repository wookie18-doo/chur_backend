import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.sql.models.enums import ImportStatus, Visibility


class DuplicateOf(BaseModel):
    """The known transaction a parsed row looks like."""

    source: Literal["existing", "pending"]
    kind: Literal["spent", "income", "pending"]
    id: str


class PendingTransactionRead(BaseModel):
    """A parsed statement row awaiting the client's save-or-decline decision."""

    id: str
    job_id: str
    filenames: list[str]
    occurred_at: date
    amount: Decimal
    kind: Literal["expense", "income"]
    currency: str | None = None
    description: str
    counterparty: str | None = None
    account_id: uuid.UUID | None = None
    suggested_category_id: int | None = None
    duplicate_of: DuplicateOf | None = Field(
        default=None,
        description="Set when the row matches a saved transaction (or another "
        "pending one); the client should advise skipping it.",
    )


class ParseJobRead(BaseModel):
    """A background statement parse, as returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ImportStatus
    filenames: list[str]
    account_id: uuid.UUID | None = None
    transaction_count: int = Field(
        description="Rows parsed; collect them from GET /transactions."
    )
    duplicate_count: int
    skipped_count: int = Field(
        description="Rows the model produced that were unusable and dropped."
    )
    error_message: str | None = None


class PendingTransactionSave(BaseModel):
    """What the client must supply to turn a parsed row into a record."""

    account_id: uuid.UUID
    category_id: int
    amount: Decimal | None = None
    occurred_at: date | None = None
    description: str | None = None
    visibility: Visibility = Visibility.PRIVATE


class SavedTransaction(BaseModel):
    """The record a pending transaction became."""

    kind: Literal["spent", "income"]
    id: uuid.UUID
