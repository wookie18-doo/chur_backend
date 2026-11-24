import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field

from app.db.sql.base import Base
from app.db.sql.models.enums import Visibility


class Income(Base, table=True):
    """A single real-world income."""

    __tablename__ = "income"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    account_id: uuid.UUID = Field(foreign_key="account.id")
    category_id: int = Field(foreign_key="category.id")
    amount: Decimal = Field(sa_column=sa.Column(sa.Numeric(12, 2), nullable=False))
    description: str | None = Field(default=None, max_length=500)
    received_at: date
    visibility: Visibility = Field(default=Visibility.PRIVATE)
    # SET NULL, not the FK default RESTRICT -- same reasoning as
    # Spent.wishlist_item_id (see that model's comment).
    planned_income_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid(), sa.ForeignKey("planned_income.id", ondelete="SET NULL")
        ),
    )
    # SET NULL: deleting a recurring rule cascades to its occurrences, and
    # must never delete or block the real incomes they were confirmed into.
    recurring_occurrence_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid(),
            sa.ForeignKey("recurring_occurrence.id", ondelete="SET NULL"),
        ),
    )
