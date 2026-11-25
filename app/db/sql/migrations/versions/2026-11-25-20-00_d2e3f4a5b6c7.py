"""Added the Nexo and Credo statement sources.

Revision ID: d2e3f4a5b6c7
Revises: bd76ee4b16fe
Create Date: 2026-11-25 20:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d2e3f4a5b6c7"
down_revision = "bd76ee4b16fe"
branch_labels = None
depends_on = None

SOURCE_NAMES = ("Nexo", "Credo")


def upgrade() -> None:
    """Run the migration."""
    for name in SOURCE_NAMES:
        op.execute(
            sa.text(
                "INSERT INTO statement_source (name) SELECT :name WHERE NOT EXISTS "
                "(SELECT 1 FROM statement_source WHERE name = :name)"
            ).bindparams(name=name)
        )


def downgrade() -> None:
    """Undo the migration."""
    for name in SOURCE_NAMES:
        op.execute(
            sa.text(
                "DELETE FROM statement_source s WHERE s.name = :name "
                "AND NOT EXISTS (SELECT 1 FROM account WHERE source_id = s.id) "
                "AND NOT EXISTS (SELECT 1 FROM import_job WHERE source_id = s.id) "
                "AND NOT EXISTS "
                "(SELECT 1 FROM imported_transaction WHERE source_id = s.id)"
            ).bindparams(name=name)
        )
