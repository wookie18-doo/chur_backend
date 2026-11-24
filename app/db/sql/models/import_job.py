import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.db.sql.base import Base
from app.db.sql.models.enums import ImportedTransactionStatus, ImportStatus
from app.db.sql.models.statement_source import StatementSourceRecord


class ImportJob(Base, table=True):
    """
    One upload: a bank/broker statement, or a market bill/receipt.

    ``source_id`` picks which parser handles the file. For a statement
    import it's derived server-side from the chosen ``Account.source``,
    never chosen directly by the client (see
    ``AccountService.require_import_source``); it's still stored here,
    denormalized off the account, since an account's own ``source``
    could change later without rewriting this job's history.
    """

    __tablename__ = "import_job"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    source_id: int = Field(foreign_key="statement_source.id")
    source_record: StatementSourceRecord = Relationship(
        sa_relationship_kwargs={"lazy": "joined"}
    )
    account_id: uuid.UUID | None = Field(default=None, foreign_key="account.id")
    original_filename: str = Field(max_length=255)
    status: ImportStatus = Field(default=ImportStatus.PENDING)
    imported_count: int = Field(default=0)
    duplicate_count: int = Field(default=0)
    failed_count: int = Field(default=0)
    error_message: str | None = Field(default=None, max_length=1000)
    # market_bill only: which existing spent to attach items to, if the
    # caller already knows. NULL for bank statements, and for a bill
    # upload with no target -- the service then looks for a single
    # obviously-matching spent, or creates a new one.
    target_spent_id: uuid.UUID | None = Field(default=None, foreign_key="spent.id")

    @property
    def source(self) -> str:
        """Code of the source whose parser handles this job."""
        return self.source_record.code


class ImportedTransaction(Base, table=True):
    """
    One parsed row from a statement import, and what became of it.

    ``user_id``/``source_id`` are denormalized off the parent ``ImportJob``
    (not just reachable through a join) purely so the dedupe uniqueness
    constraint below can be expressed directly on this table.
    """

    __tablename__ = "imported_transaction"
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "source_id", "dedupe_key", name="uq_imported_transaction_dedupe"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    import_job_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid(), sa.ForeignKey("import_job.id", ondelete="CASCADE"), index=True
        )
    )
    user_id: uuid.UUID = Field(foreign_key="user.id")
    source_id: int = Field(foreign_key="statement_source.id")
    dedupe_key: str = Field(max_length=255)
    spent_id: uuid.UUID | None = Field(default=None, foreign_key="spent.id")
    income_id: uuid.UUID | None = Field(default=None, foreign_key="income.id")
    raw_payload: dict[str, Any] = Field(sa_column=sa.Column(sa.JSON, nullable=False))
    status: ImportedTransactionStatus
