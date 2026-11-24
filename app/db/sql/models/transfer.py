import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field

from app.db.sql.base import Base
from app.db.sql.models.enums import Visibility


class Transfer(Base, table=True):
    """
    Money moved between two accounts inside the household.

    Its own table, not a ``Spent``+``Income`` pair, so it never touches
    income/spend totals. ``amount`` leaves ``from_account_id`` in its
    currency; ``to_amount`` arrives in ``to_account_id``'s.
    """

    __tablename__ = "transfer"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    from_account_id: uuid.UUID = Field(foreign_key="account.id", index=True)
    to_account_id: uuid.UUID = Field(foreign_key="account.id", index=True)
    amount: Decimal = Field(sa_column=sa.Column(sa.Numeric(12, 2), nullable=False))
    to_amount: Decimal = Field(sa_column=sa.Column(sa.Numeric(12, 2), nullable=False))
    description: str | None = Field(default=None, max_length=500)
    transferred_at: date
    visibility: Visibility = Field(default=Visibility.PRIVATE)
