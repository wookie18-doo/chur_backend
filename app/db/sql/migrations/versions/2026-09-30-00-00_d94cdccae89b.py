"""Added import_job and imported_transaction models.

Revision ID: d94cdccae89b
Revises: 4fad083fd585
Create Date: 2026-09-30 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d94cdccae89b"
down_revision = "4fad083fd585"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    op.create_table(
        "import_job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("target_spent_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(["target_spent_id"], ["spent.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_import_job_user_id"), "import_job", ["user_id"])

    op.create_table(
        "imported_transaction",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_job_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("spent_id", sa.Uuid(), nullable=True),
        sa.Column("income_id", sa.Uuid(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
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
            ["import_job_id"], ["import_job.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["spent_id"], ["spent.id"]),
        sa.ForeignKeyConstraint(["income_id"], ["income.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "source", "dedupe_key", name="uq_imported_transaction_dedupe"
        ),
    )
    op.create_index(
        op.f("ix_imported_transaction_import_job_id"),
        "imported_transaction",
        ["import_job_id"],
    )


def downgrade() -> None:
    """Undo the migration."""
    op.drop_index(
        op.f("ix_imported_transaction_import_job_id"),
        table_name="imported_transaction",
    )
    op.drop_table("imported_transaction")
    op.drop_index(op.f("ix_import_job_user_id"), table_name="import_job")
    op.drop_table("import_job")
