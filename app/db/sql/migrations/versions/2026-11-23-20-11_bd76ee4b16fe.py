"""Aligned nullability and unique constraints with the models.

Revision ID: bd76ee4b16fe
Revises: c1d2e3f4a5b6
Create Date: 2026-11-23 20:11:38.048155

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "bd76ee4b16fe"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    op.alter_column(
        "imported_transaction", "import_job_id", existing_type=sa.UUID(), nullable=True
    )
    op.drop_index(op.f("ix_permission_name"), table_name="permission")
    op.create_unique_constraint("permission_name_key", "permission", ["name"])
    op.drop_index(op.f("ix_role_name"), table_name="role")
    op.create_unique_constraint("role_name_key", "role", ["name"])
    op.alter_column("spent_item", "spent_id", existing_type=sa.UUID(), nullable=True)
    op.drop_index(op.f("ix_user_phone"), table_name="user")
    op.drop_index(op.f("ix_user_username"), table_name="user")
    op.create_unique_constraint("user_username_key", "user", ["username"])
    op.create_unique_constraint("user_phone_key", "user", ["phone"])
    op.alter_column(
        "wishlist_item", "wishlist_id", existing_type=sa.UUID(), nullable=True
    )


def downgrade() -> None:
    """Undo the migration."""
    op.alter_column(
        "wishlist_item", "wishlist_id", existing_type=sa.UUID(), nullable=False
    )
    op.drop_constraint("user_username_key", "user", type_="unique")
    op.drop_constraint("user_phone_key", "user", type_="unique")
    op.create_index(op.f("ix_user_username"), "user", ["username"], unique=True)
    op.create_index(op.f("ix_user_phone"), "user", ["phone"], unique=True)
    op.alter_column("spent_item", "spent_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint("role_name_key", "role", type_="unique")
    op.create_index(op.f("ix_role_name"), "role", ["name"], unique=True)
    op.drop_constraint("permission_name_key", "permission", type_="unique")
    op.create_index(op.f("ix_permission_name"), "permission", ["name"], unique=True)
    op.alter_column(
        "imported_transaction", "import_job_id", existing_type=sa.UUID(), nullable=False
    )
