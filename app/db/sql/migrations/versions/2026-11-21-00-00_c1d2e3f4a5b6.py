"""Added repeat settings to wishlist items and planned incomes.

Revision ID: c1d2e3f4a5b6
Revises: b9d5f7a1c3e6
Create Date: 2026-11-21 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c1d2e3f4a5b6"
down_revision = "b9d5f7a1c3e6"
branch_labels = None
depends_on = None

TABLES = ("wishlist_item", "planned_income")


def upgrade() -> None:
    """Run the migration."""
    frequency = postgresql.ENUM(name="recurrencefrequency", create_type=False)
    for table in TABLES:
        op.add_column(table, sa.Column("frequency", frequency, nullable=True))
        op.add_column(table, sa.Column("repeat_until", sa.Date(), nullable=True))
        op.add_column(table, sa.Column("repeat_anchor_day", sa.Integer(), nullable=True))
    op.add_column("wishlist_item", sa.Column("planned_date_to", sa.Date(), nullable=True))


def downgrade() -> None:
    """Undo the migration."""
    op.drop_column("wishlist_item", "planned_date_to")
    for table in TABLES:
        op.drop_column(table, "repeat_anchor_day")
        op.drop_column(table, "repeat_until")
        op.drop_column(table, "frequency")
