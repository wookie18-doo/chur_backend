"""Added planned_income model and linked income to it.

Revision ID: 30c15a80f711
Revises: c19cdd77b72f
Create Date: 2026-09-27 00:50:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "30c15a80f711"
down_revision = "c19cdd77b72f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    op.create_table(
        "planned_income",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("realised_income_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.ForeignKeyConstraint(
            ["realised_income_id"], ["income.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_planned_income_user_id"), "planned_income", ["user_id"]
    )

    op.add_column(
        "income", sa.Column("planned_income_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_income_planned_income_id_planned_income"),
        "income",
        "planned_income",
        ["planned_income_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Undo the migration."""
    op.drop_constraint(
        op.f("fk_income_planned_income_id_planned_income"),
        "income",
        type_="foreignkey",
    )
    op.drop_column("income", "planned_income_id")
    op.drop_index(op.f("ix_planned_income_user_id"), table_name="planned_income")
    op.drop_table("planned_income")
