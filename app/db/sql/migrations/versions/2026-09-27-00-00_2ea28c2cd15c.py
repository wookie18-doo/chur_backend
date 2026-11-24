"""Added family grouping models.

Revision ID: 2ea28c2cd15c
Revises: f3a9c1d2e4b6
Create Date: 2026-09-27 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "2ea28c2cd15c"
down_revision = "f3a9c1d2e4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    op.create_table(
        "family",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
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

    op.create_table(
        "family_member",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["family_id"], ["family.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_family_member_family_id"), "family_member", ["family_id"]
    )


def downgrade() -> None:
    """Undo the migration."""
    op.drop_index(op.f("ix_family_member_family_id"), table_name="family_member")
    op.drop_table("family_member")
    op.drop_table("family")
