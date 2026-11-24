import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.db.sql.models.enums import ImportedTransactionStatus, ImportStatus


class ImportJobRead(BaseModel):
    """Represents an import job returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    account_id: uuid.UUID | None = None
    original_filename: str
    status: ImportStatus
    imported_count: int
    duplicate_count: int
    failed_count: int
    error_message: str | None = None
    target_spent_id: uuid.UUID | None = None


class ImportedTransactionRead(BaseModel):
    """Represents one parsed row from an import job, as returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dedupe_key: str
    spent_id: uuid.UUID | None = None
    income_id: uuid.UUID | None = None
    raw_payload: dict[str, Any]
    status: ImportedTransactionStatus
