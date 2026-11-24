import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field

from app.db.sql.base import Base
from app.db.sql.models.enums import PlanStatus, RecurrenceFrequency, Visibility


class PlannedIncome(Base, table=True):
    """
    An expected future income, optionally scoped to a date range.

    Flat (no container list, unlike ``Wishlist``/``WishlistItem``) --
    planning incomes doesn't need the list/grouping concept planning
    spending does, just the item lifecycle. ``realised_income_id`` is
    ``SET NULL`` (not blocked) if the linked ``Income`` is later deleted,
    the same documented tradeoff as ``WishlistItem.realised_spent_id``.
    """

    __tablename__ = "planned_income"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    category_id: int = Field(foreign_key="category.id")
    name: str = Field(max_length=200)
    amount: Decimal = Field(sa_column=sa.Column(sa.Numeric(12, 2), nullable=False))
    date_from: date | None = Field(default=None)
    date_to: date | None = Field(default=None)
    visibility: Visibility = Field(default=Visibility.PRIVATE)
    status: PlanStatus = Field(default=PlanStatus.PLANNED)
    realised_income_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(sa.Uuid(), sa.ForeignKey("income.id", ondelete="SET NULL")),
    )
    # SET NULL: deleting an account only clears the plan's account hint.
    account_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid(), sa.ForeignKey("account.id", ondelete="SET NULL")
        ),
    )
    # Realising a repeating plan rolls the window forward instead of closing it.
    frequency: RecurrenceFrequency | None = Field(default=None)
    repeat_until: date | None = Field(default=None)
    repeat_anchor_day: int | None = Field(default=None)
