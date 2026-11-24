"""Added wishlist models and linked spent to wishlist_item.

Revision ID: c19cdd77b72f
Revises: 47f9cb3b55fe
Create Date: 2026-09-27 00:40:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c19cdd77b72f"
down_revision = "47f9cb3b55fe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    op.create_table(
        "wishlist",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wishlist_user_id"), "wishlist", ["user_id"])

    op.create_table(
        "wishlist_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wishlist_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("realised_spent_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(["wishlist_id"], ["wishlist.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
        sa.ForeignKeyConstraint(
            ["realised_spent_id"], ["spent.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_wishlist_item_wishlist_id"), "wishlist_item", ["wishlist_id"]
    )

    op.add_column("spent", sa.Column("wishlist_item_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_spent_wishlist_item_id_wishlist_item"),
        "spent",
        "wishlist_item",
        ["wishlist_item_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Undo the migration."""
    op.drop_constraint(
        op.f("fk_spent_wishlist_item_id_wishlist_item"), "spent", type_="foreignkey"
    )
    op.drop_column("spent", "wishlist_item_id")
    op.drop_index(op.f("ix_wishlist_item_wishlist_id"), table_name="wishlist_item")
    op.drop_table("wishlist_item")
    op.drop_index(op.f("ix_wishlist_user_id"), table_name="wishlist")
    op.drop_table("wishlist")
