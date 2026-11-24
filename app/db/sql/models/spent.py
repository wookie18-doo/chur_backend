import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field

from app.db.sql.base import Base
from app.db.sql.models.enums import Visibility


class Spent(Base, table=True):
    """A single real-world expense."""

    __tablename__ = "spent"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    account_id: uuid.UUID = Field(foreign_key="account.id")
    category_id: int = Field(foreign_key="category.id")
    amount: Decimal = Field(sa_column=sa.Column(sa.Numeric(12, 2), nullable=False))
    description: str | None = Field(default=None, max_length=500)
    spent_at: date
    visibility: Visibility = Field(default=Visibility.PRIVATE)
    # SET NULL, not the FK default RESTRICT: deleting a wishlist cascades
    # to its items, and a realised spent must never block -- or be
    # dragged into -- that delete just because it's linked back to one.
    wishlist_item_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid(), sa.ForeignKey("wishlist_item.id", ondelete="SET NULL")
        ),
    )
    # SET NULL: deleting a recurring rule cascades to its occurrences, and
    # must never delete or block the real spents they were confirmed into.
    recurring_occurrence_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid(),
            sa.ForeignKey("recurring_occurrence.id", ondelete="SET NULL"),
        ),
    )


class SpentItem(Base, table=True):
    """
    One product/line item a ``Spent`` was itemized into from a receipt.

    Purely a drill-down attached to its parent -- see the "Splitting a
    spent into line items" section of the build plan. Never used to
    derive or validate the parent's own ``amount``.
    """

    __tablename__ = "spent_item"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    spent_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid(), sa.ForeignKey("spent.id", ondelete="CASCADE"), index=True
        )
    )
    category_id: int | None = Field(default=None, foreign_key="category.id")
    name: str = Field(max_length=200)
    amount: Decimal = Field(sa_column=sa.Column(sa.Numeric(12, 2), nullable=False))
    quantity: str | None = Field(default=None, max_length=50)
