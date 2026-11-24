"""Added currency and exchange_rate, seeding the supported currencies.

Revision ID: b7d3f1a8c5e2
Revises: a1c7e9d2b3f4
Create Date: 2026-10-11 00:10:00.000000

"""

import sqlalchemy as sa
from alembic import op

from app.db.sql.seed_data import BUILTIN_CURRENCIES

# revision identifiers, used by Alembic.
revision = "b7d3f1a8c5e2"
down_revision = "a1c7e9d2b3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    currency_table = op.create_table(
        "currency",
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("code"),
    )
    op.bulk_insert(currency_table, BUILTIN_CURRENCIES)

    op.create_table(
        "exchange_rate",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["currency_code"], ["currency.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "currency_code", "base_currency", "as_of", name="uq_exchange_rate_day"
        ),
    )


def downgrade() -> None:
    """Undo the migration."""
    op.drop_table("exchange_rate")
    op.drop_table("currency")
