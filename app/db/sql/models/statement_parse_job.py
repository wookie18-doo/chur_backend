import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field

from app.db.sql.base import Base
from app.db.sql.models.enums import ImportStatus


class StatementParseJob(Base, table=True):
    """
    One background LLM parse of uploaded statement files.

    Holds only the job's progress and counts -- never the uploaded files or
    the parsed rows, which live in the short-lived pending-transaction cache.
    """

    __tablename__ = "statement_parse_job"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    # SET NULL: a finished job must never block deleting its account.
    account_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid(), sa.ForeignKey("account.id", ondelete="SET NULL")
        ),
    )
    filenames: list[Any] = Field(sa_column=sa.Column(sa.JSON, nullable=False))
    status: ImportStatus = Field(default=ImportStatus.PENDING)
    transaction_count: int = Field(default=0)
    duplicate_count: int = Field(default=0)
    skipped_count: int = Field(default=0)
    error_message: str | None = Field(default=None, max_length=1000)
