import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field

from app.db.sql.base import Base
from app.db.sql.models.enums import PlanStatus, RecurrenceFrequency, Visibility


class Wishlist(Base, table=True):
    """A planned-spending list, optionally scoped to a date range."""

    __tablename__ = "wishlist"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=500)
    date_from: date | None = Field(default=None)
    date_to: date | None = Field(default=None)
    visibility: Visibility = Field(default=Visibility.PRIVATE)


class WishlistItem(Base, table=True):
    """
    One planned purchase on a wishlist.

    ``visibility = NULL`` inherits the parent wishlist's own visibility;
    a set value overrides it for this item alone. ``realised_spent_id``
    is set to ``NULL`` (not blocked) if the linked ``Spent`` is later
    deleted -- the item's ``status`` stays ``REALISED`` with no linked
    spent in that edge case, a documented MVP tradeoff rather than a
    cross-service cascade (deleting a spent shouldn't need
    ``SpentService`` to know about wishlists at all).
    """

    __tablename__ = "wishlist_item"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    wishlist_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid(), sa.ForeignKey("wishlist.id", ondelete="CASCADE"), index=True
        )
    )
    category_id: int = Field(foreign_key="category.id")
    name: str = Field(max_length=200)
    amount: Decimal = Field(sa_column=sa.Column(sa.Numeric(12, 2), nullable=False))
    planned_date: date | None = Field(default=None)
    planned_date_to: date | None = Field(default=None)
    visibility: Visibility | None = Field(default=None)
    status: PlanStatus = Field(default=PlanStatus.PLANNED)
    realised_spent_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(sa.Uuid(), sa.ForeignKey("spent.id", ondelete="SET NULL")),
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
