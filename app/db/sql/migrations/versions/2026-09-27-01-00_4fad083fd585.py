"""Added recurring_transaction model and linked spent/income to it.

Revision ID: 4fad083fd585
Revises: 30c15a80f711
Create Date: 2026-09-27 01:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "4fad083fd585"
down_revision = "30c15a80f711"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    op.create_table(
        "recurring_transaction",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("next_run_at", sa.Date(), nullable=False),
        sa.Column("last_realised_at", sa.Date(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recurring_transaction_user_id"), "recurring_transaction", ["user_id"]
    )
    op.create_index(
        op.f("ix_recurring_transaction_next_run_at"),
        "recurring_transaction",
        ["next_run_at"],
    )

    op.add_column(
        "spent", sa.Column("recurring_transaction_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_spent_recurring_transaction_id_recurring_transaction"),
        "spent",
        "recurring_transaction",
        ["recurring_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "income", sa.Column("recurring_transaction_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_income_recurring_transaction_id_recurring_transaction"),
        "income",
        "recurring_transaction",
        ["recurring_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Undo the migration."""
    op.drop_constraint(
        op.f("fk_income_recurring_transaction_id_recurring_transaction"),
        "income",
        type_="foreignkey",
    )
    op.drop_column("income", "recurring_transaction_id")
    op.drop_constraint(
        op.f("fk_spent_recurring_transaction_id_recurring_transaction"),
        "spent",
        type_="foreignkey",
    )
    op.drop_column("spent", "recurring_transaction_id")
    op.drop_index(
        op.f("ix_recurring_transaction_next_run_at"),
        table_name="recurring_transaction",
    )
    op.drop_index(
        op.f("ix_recurring_transaction_user_id"), table_name="recurring_transaction"
    )
    op.drop_table("recurring_transaction")
