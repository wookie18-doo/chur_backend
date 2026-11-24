"""Added spent, spent_item, and income models.

Revision ID: 47f9cb3b55fe
Revises: b2ab8473bdc5
Create Date: 2026-09-27 00:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "47f9cb3b55fe"
down_revision = "b2ab8473bdc5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    op.create_table(
        "spent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("spent_at", sa.Date(), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
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
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_spent_user_id"), "spent", ["user_id"])

    op.create_table(
        "spent_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("spent_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.String(length=50), nullable=True),
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
        sa.ForeignKeyConstraint(["spent_id"], ["spent.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_spent_item_spent_id"), "spent_item", ["spent_id"])

    op.create_table(
        "income",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("received_at", sa.Date(), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
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
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_income_user_id"), "income", ["user_id"])


def downgrade() -> None:
    """Undo the migration."""
    op.drop_index(op.f("ix_income_user_id"), table_name="income")
    op.drop_table("income")
    op.drop_index(op.f("ix_spent_item_spent_id"), table_name="spent_item")
    op.drop_table("spent_item")
    op.drop_index(op.f("ix_spent_user_id"), table_name="spent")
    op.drop_table("spent")
