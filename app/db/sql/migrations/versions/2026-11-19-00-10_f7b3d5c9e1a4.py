"""Added the statement_source table.

Revision ID: f7b3d5c9e1a4
Revises: e6a2c4b8d0f3
Create Date: 2026-11-19 00:10:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f7b3d5c9e1a4"
down_revision = "e6a2c4b8d0f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    op.create_table(
        "statement_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_statement_source_name"), "statement_source", ["name"], unique=True
    )


def downgrade() -> None:
    """Undo the migration."""
    op.drop_index(op.f("ix_statement_source_name"), table_name="statement_source")
    op.drop_table("statement_source")
