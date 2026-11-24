import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field

from app.db.sql.base import Base


class Currency(Base, table=True):
    """
    An ISO 4217 currency accounts may be denominated in.

    Reference data: seeded by a migration, never edited through the API.
    ``is_active = False`` stops offering it for new accounts without
    breaking existing ones.
    """

    __tablename__ = "currency"

    code: str = Field(max_length=3, primary_key=True)
    name: str = Field(max_length=100)
    is_active: bool = Field(default=True)


class ExchangeRate(Base, table=True):
    """
    One day's rate of a currency against a base currency.

    One row per ``(currency_code, base_currency, as_of)`` -- append-only
    history, upserted when the daily job re-runs on the same day.
    """

    __tablename__ = "exchange_rate"
    __table_args__ = (
        sa.UniqueConstraint(
            "currency_code", "base_currency", "as_of", name="uq_exchange_rate_day"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    currency_code: str = Field(foreign_key="currency.code", max_length=3)
    base_currency: str = Field(max_length=3)
    rate: Decimal = Field(sa_column=sa.Column(sa.Numeric(18, 8), nullable=False))
    as_of: date
    fetched_at: datetime = Field(
        sa_column=sa.Column(
            sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        )
    )
