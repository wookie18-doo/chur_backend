"""Replaced the statementsource enum columns with statement_source foreign keys.

Revision ID: a8c4e6f0b2d5
Revises: f7b3d5c9e1a4
Create Date: 2026-11-19 00:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a8c4e6f0b2d5"
down_revision = "f7b3d5c9e1a4"
branch_labels = None
depends_on = None

TABLES = ("account", "import_job", "imported_transaction")
# Enum labels are member names, upper-cased code: WISE, MARKET_BILL, ...
SOURCE_NAMES = {
    "WISE": "Wise",
    "BUNQ": "Bunq",
    "DUKASCOPY": "Dukascopy",
    "DEBLOCK": "Deblock",
    "MARKET_BILL": "Market bill",
}
LABEL_SQL = "upper(regexp_replace(s.name, '[^A-Za-z0-9]+', '_', 'g'))"


def upgrade() -> None:
    """Run the migration."""
    for name in SOURCE_NAMES.values():
        op.execute(
            sa.text(
                "INSERT INTO statement_source (name) "
                "SELECT :name WHERE NOT EXISTS "
                "(SELECT 1 FROM statement_source WHERE name = :name)"
            ).bindparams(name=name)
        )
    for table in TABLES:
        op.add_column(table, sa.Column("source_id", sa.Integer(), nullable=True))
        op.execute(
            f'UPDATE "{table}" t SET source_id = s.id FROM statement_source s '  # noqa: S608
            f"WHERE t.source::text = {LABEL_SQL}"
        )
        op.create_foreign_key(
            f"fk_{table}_source_id", table, "statement_source", ["source_id"], ["id"]
        )
    op.alter_column("import_job", "source_id", nullable=False)
    op.alter_column("imported_transaction", "source_id", nullable=False)

    op.drop_constraint(
        "uq_imported_transaction_dedupe", "imported_transaction", type_="unique"
    )
    op.create_unique_constraint(
        "uq_imported_transaction_dedupe",
        "imported_transaction",
        ["user_id", "source_id", "dedupe_key"],
    )
    for table in TABLES:
        op.drop_column(table, "source")
    op.execute("DROP TYPE statementsource")


def downgrade() -> None:
    """Undo the migration."""
    labels = ", ".join(f"'{label}'" for label in SOURCE_NAMES)
    op.execute(f"CREATE TYPE statementsource AS ENUM ({labels})")
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "source",
                sa.Enum(*SOURCE_NAMES, name="statementsource", create_type=False),
                nullable=True,
            ),
        )
        op.execute(
            f'UPDATE "{table}" t SET source = ({LABEL_SQL})::statementsource '  # noqa: S608
            f"FROM statement_source s WHERE t.source_id = s.id "
            f"AND {LABEL_SQL} IN ({labels})"
        )
    op.alter_column("import_job", "source", nullable=False)
    op.alter_column("imported_transaction", "source", nullable=False)

    op.drop_constraint(
        "uq_imported_transaction_dedupe", "imported_transaction", type_="unique"
    )
    op.create_unique_constraint(
        "uq_imported_transaction_dedupe",
        "imported_transaction",
        ["user_id", "source", "dedupe_key"],
    )
    for table in TABLES:
        op.drop_constraint(f"fk_{table}_source_id", table, type_="foreignkey")
        op.drop_column(table, "source_id")
