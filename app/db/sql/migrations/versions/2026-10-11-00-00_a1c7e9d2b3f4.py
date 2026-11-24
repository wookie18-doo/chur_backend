"""Added recurring_occurrence and repointed spent/income at it.

Revision ID: a1c7e9d2b3f4
Revises: d94cdccae89b
Create Date: 2026-10-11 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1c7e9d2b3f4"
down_revision = "d94cdccae89b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    op.create_table(
        "recurring_occurrence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recurring_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("completed_at", sa.Date(), nullable=True),
        sa.Column("spent_id", sa.Uuid(), nullable=True),
        sa.Column("income_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["recurring_transaction_id"],
            ["recurring_transaction.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["spent_id"], ["spent.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["income_id"], ["income.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recurring_occurrence_recurring_transaction_id"),
        "recurring_occurrence",
        ["recurring_transaction_id"],
    )
    op.alter_column(
        "recurring_transaction",
        "last_realised_at",
        new_column_name="last_generated_at",
    )

    for table in ("spent", "income"):
        op.add_column(
            table, sa.Column("recurring_occurrence_id", sa.Uuid(), nullable=True)
        )
        op.create_foreign_key(
            f"fk_{table}_recurring_occurrence_id",
            table,
            "recurring_occurrence",
            ["recurring_occurrence_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Backfill: each record the old design auto-posted becomes a confirmed
    # occurrence, so the new link is populated before the old one is dropped.
    for table, link, date_col in (
        ("spent", "spent_id", "spent_at"),
        ("income", "income_id", "received_at"),
    ):
        op.execute(
            f"INSERT INTO recurring_occurrence (id, recurring_transaction_id, "  # noqa: S608
            f"due_date, status, completed_at, {link}) "
            f"SELECT gen_random_uuid(), recurring_transaction_id, {date_col}, "
            f"'realised', {date_col}, id FROM {table} "
            f"WHERE recurring_transaction_id IS NOT NULL"
        )
        op.execute(
            f"UPDATE {table} SET recurring_occurrence_id = o.id "  # noqa: S608
            f"FROM recurring_occurrence o WHERE o.{link} = {table}.id"
        )
        op.drop_column(table, "recurring_transaction_id")


def downgrade() -> None:
    """Undo the migration."""
    for table, link in (("income", "income_id"), ("spent", "spent_id")):
        op.add_column(
            table,
            sa.Column("recurring_transaction_id", sa.Uuid(), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_recurring_transaction_id",
            table,
            "recurring_transaction",
            ["recurring_transaction_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.execute(
            f"UPDATE {table} SET recurring_transaction_id = o.recurring_transaction_id "  # noqa: S608,E501
            f"FROM recurring_occurrence o WHERE o.{link} = {table}.id"
        )
        op.drop_constraint(
            f"fk_{table}_recurring_occurrence_id", table, type_="foreignkey"
        )
        op.drop_column(table, "recurring_occurrence_id")
    op.alter_column(
        "recurring_transaction",
        "last_generated_at",
        new_column_name="last_realised_at",
    )
    op.drop_index(
        op.f("ix_recurring_occurrence_recurring_transaction_id"),
        table_name="recurring_occurrence",
    )
    op.drop_table("recurring_occurrence")
