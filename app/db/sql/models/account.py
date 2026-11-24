import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.db.sql.base import Base
from app.db.sql.models.enums import AccountKind
from app.db.sql.models.statement_source import StatementSourceRecord


class Account(Base, table=True):
    """
    A bank account, card, cash wallet, or broker account.

    Every ``Spent``/``Income`` names which of a user's accounts it moved
    through (Phase 4). ``source_id`` names which automated import parser (if
    any) feeds this account -- ``NULL`` for a manually-tracked account
    like plain cash.
    """

    __tablename__ = "account"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    name: str = Field(max_length=200)
    kind: AccountKind
    currency: str = Field(max_length=3)
    source_id: int | None = Field(default=None, foreign_key="statement_source.id")
    source_record: StatementSourceRecord | None = Relationship(
        sa_relationship_kwargs={"lazy": "joined"}
    )
    is_active: bool = Field(default=True)
    opening_balance: Decimal | None = Field(
        default=None, sa_column=sa.Column(sa.Numeric(12, 2), nullable=True)
    )
    # CASCADE: a jar/card is structural detail of its parent, not ledger
    # history, so deleting the parent deletes its sub-accounts with it.
    parent_account_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            index=True,
            nullable=True,
        ),
    )
    is_savings: bool = Field(
        default=False,
        sa_column=sa.Column(sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    @property
    def source(self) -> str | None:
        """Code of the import source feeding this account, if any."""
        return self.source_record.code if self.source_record else None


class BalanceAdjustment(Base, table=True):
    """
    A manual correction/seed entry on an account's balance.

    Not economic activity -- nothing was bought, earned, or moved -- so it
    never counts in reports. Append-only: corrections add rows.
    """

    __tablename__ = "balance_adjustment"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    account_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    delta: Decimal = Field(sa_column=sa.Column(sa.Numeric(12, 2), nullable=False))
    reason: str | None = Field(default=None, max_length=500)
    adjusted_at: date
