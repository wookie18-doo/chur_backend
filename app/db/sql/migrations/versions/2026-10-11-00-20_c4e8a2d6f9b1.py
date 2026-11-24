"""Added jars, savings flag, balance adjustments and transfers.

Revision ID: c4e8a2d6f9b1
Revises: b7d3f1a8c5e2
Create Date: 2026-10-11 00:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4e8a2d6f9b1"
down_revision = "b7d3f1a8c5e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    op.add_column("account", sa.Column("parent_account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_account_parent_account_id",
        "account",
        "account",
        ["parent_account_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_account_parent_account_id"), "account", ["parent_account_id"]
    )
    op.add_column(
        "account",
        sa.Column(
            "is_savings", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )

    for table in ("wishlist_item", "planned_income"):
        op.add_column(table, sa.Column("account_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_account_id",
            table,
            "account",
            ["account_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "balance_adjustment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("delta", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("adjusted_at", sa.Date(), nullable=False),
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
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_balance_adjustment_user_id"), "balance_adjustment", ["user_id"]
    )
    op.create_index(
        op.f("ix_balance_adjustment_account_id"), "balance_adjustment", ["account_id"]
    )

    op.create_table(
        "transfer",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("from_account_id", sa.Uuid(), nullable=False),
        sa.Column("to_account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("to_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("transferred_at", sa.Date(), nullable=False),
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
        sa.ForeignKeyConstraint(["from_account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["to_account_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transfer_user_id"), "transfer", ["user_id"])
    op.create_index(
        op.f("ix_transfer_from_account_id"), "transfer", ["from_account_id"]
    )
    op.create_index(op.f("ix_transfer_to_account_id"), "transfer", ["to_account_id"])


def downgrade() -> None:
    """Undo the migration."""
    op.drop_table("transfer")
    op.drop_table("balance_adjustment")
    for table in ("planned_income", "wishlist_item"):
        op.drop_constraint(f"fk_{table}_account_id", table, type_="foreignkey")
        op.drop_column(table, "account_id")
    op.drop_column("account", "is_savings")
    op.drop_index(op.f("ix_account_parent_account_id"), table_name="account")
    op.drop_constraint("fk_account_parent_account_id", "account", type_="foreignkey")
    op.drop_column("account", "parent_account_id")
