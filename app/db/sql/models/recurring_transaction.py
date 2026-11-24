import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field

from app.db.sql.base import Base
from app.db.sql.models.enums import (
    CategoryKind,
    PlanStatus,
    RecurrenceFrequency,
    Visibility,
)


class RecurringTransaction(Base, table=True):
    """
    A rule that auto-generates real ``Spent``/``Income`` rows on a schedule.

    Single table for both directions (mirrors ``Category.kind``) to
    avoid duplicating recurrence logic across two near-identical tables.
    ``kind`` must match the referenced category's own kind -- enforced
    in the service, not the DB.
    """

    __tablename__ = "recurring_transaction"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    account_id: uuid.UUID = Field(foreign_key="account.id")
    kind: CategoryKind
    category_id: int = Field(foreign_key="category.id")
    amount: Decimal = Field(sa_column=sa.Column(sa.Numeric(12, 2), nullable=False))
    description: str | None = Field(default=None, max_length=500)
    visibility: Visibility = Field(default=Visibility.PRIVATE)

    frequency: RecurrenceFrequency
    interval: int = Field(default=1)
    day_of_month: int | None = Field(default=None)
    weekday: int | None = Field(default=None)
    start_date: date
    end_date: date | None = Field(default=None)

    next_run_at: date = Field(index=True)
    last_generated_at: date | None = Field(default=None)
    is_active: bool = Field(default=True)


class RecurringOccurrence(Base, table=True):
    """
    One due date a recurring rule has generated, and what became of it.

    ``PLANNED`` means generated but not yet confirmed; ``REALISED`` means
    the user confirmed it and a ``Spent``/``Income`` was posted (or
    linked). ``due_date`` is the schedule's own date and never changes;
    ``completed_at`` is when it actually happened and stays editable.
    """

    __tablename__ = "recurring_occurrence"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    recurring_transaction_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid(),
            sa.ForeignKey("recurring_transaction.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    due_date: date
    status: PlanStatus = Field(default=PlanStatus.PLANNED)
    completed_at: date | None = Field(default=None)
    # SET NULL: deleting the posted record must not delete the history row.
    spent_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(sa.Uuid(), sa.ForeignKey("spent.id", ondelete="SET NULL")),
    )
    income_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(sa.Uuid(), sa.ForeignKey("income.id", ondelete="SET NULL")),
    )
