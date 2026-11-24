"""Added the Revolut statement source.

Revision ID: b9d5f7a1c3e6
Revises: a8c4e6f0b2d5
Create Date: 2026-11-19 00:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b9d5f7a1c3e6"
down_revision = "a8c4e6f0b2d5"
branch_labels = None
depends_on = None

SOURCE_NAME = "Revolut"


def upgrade() -> None:
    """Run the migration."""
    op.execute(
        sa.text(
            "INSERT INTO statement_source (name) SELECT :name WHERE NOT EXISTS "
            "(SELECT 1 FROM statement_source WHERE name = :name)"
        ).bindparams(name=SOURCE_NAME)
    )


def downgrade() -> None:
    """Undo the migration."""
    op.execute(
        sa.text(
            "DELETE FROM statement_source s WHERE s.name = :name "
            "AND NOT EXISTS (SELECT 1 FROM account WHERE source_id = s.id) "
            "AND NOT EXISTS (SELECT 1 FROM import_job WHERE source_id = s.id) "
            "AND NOT EXISTS "
            "(SELECT 1 FROM imported_transaction WHERE source_id = s.id)"
        ).bindparams(name=SOURCE_NAME)
    )
