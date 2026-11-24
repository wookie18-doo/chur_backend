"""Added category model and seeded the built-in categories.

Revision ID: 2c3f9788357a
Revises: 2ea28c2cd15c
Create Date: 2026-09-27 00:10:00.000000

"""

import sqlalchemy as sa
from alembic import op

from app.db.sql.seed_data import BUILTIN_CATEGORIES

# revision identifiers, used by Alembic.
revision = "2c3f9788357a"
down_revision = "2ea28c2cd15c"
branch_labels = None
depends_on = None

category_table = sa.table(
    "category",
    sa.column("name", sa.String),
    sa.column("kind", sa.String),
    sa.column("owner_id", sa.Uuid),
    sa.column("color", sa.String),
)


def upgrade() -> None:
    """Run the migration."""
    op.create_table(
        "category",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
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
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(category_table, BUILTIN_CATEGORIES)


def downgrade() -> None:
    """Undo the migration."""
    op.drop_table("category")
