"""Converted enum columns from VARCHAR to native Postgres enum types.

Revision ID: e6a2c4b8d0f3
Revises: d5f1b3a7c9e2
Create Date: 2026-11-19 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "e6a2c4b8d0f3"
down_revision = "d5f1b3a7c9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Run the migration."""
    for name, values in ENUM_TYPES.items():
        labels = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({labels})")
    for table, column, enum_name in ENUM_COLUMNS:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
            f'TYPE {enum_name} USING upper("{column}")::{enum_name}'
        )


def downgrade() -> None:
    """Undo the migration."""
    for table, column, _ in ENUM_COLUMNS:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
            f'TYPE VARCHAR(20) USING "{column}"::text'
        )
    for name in ENUM_TYPES:
        op.execute(f"DROP TYPE {name}")


# Labels are member names: SQLAlchemy persists Enum members by name.
ENUM_TYPES = {
    "visibility": ("PRIVATE", "FAMILY"),
    "familyrole": ("OWNER", "MEMBER"),
    "categorykind": ("EXPENSE", "INCOME"),
    "categorycolor": ("CLAY", "BLUE", "VIOLET", "OCHRE", "TEAL"),
    "planstatus": ("PLANNED", "REALISED"),
    "recurrencefrequency": ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"),
    "accountkind": ("BANK", "CASH", "CARD", "BROKER", "JAR", "OTHER"),
    "importstatus": ("PENDING", "PROCESSING", "COMPLETED", "FAILED"),
    "importedtransactionstatus": ("IMPORTED", "DUPLICATE_SKIPPED", "FAILED"),
    "statementsource": ("WISE", "BUNQ", "DUKASCOPY", "DEBLOCK", "MARKET_BILL"),
}

ENUM_COLUMNS = (
    ("account", "kind", "accountkind"),
    ("account", "source", "statementsource"),
    ("category", "kind", "categorykind"),
    ("category", "color", "categorycolor"),
    ("family_member", "role", "familyrole"),
    ("import_job", "source", "statementsource"),
    ("import_job", "status", "importstatus"),
    ("imported_transaction", "source", "statementsource"),
    ("imported_transaction", "status", "importedtransactionstatus"),
    ("income", "visibility", "visibility"),
    ("planned_income", "visibility", "visibility"),
    ("planned_income", "status", "planstatus"),
    ("recurring_occurrence", "status", "planstatus"),
    ("recurring_transaction", "kind", "categorykind"),
    ("recurring_transaction", "visibility", "visibility"),
    ("recurring_transaction", "frequency", "recurrencefrequency"),
    ("spent", "visibility", "visibility"),
    ("statement_parse_job", "status", "importstatus"),
    ("transfer", "visibility", "visibility"),
    ("wishlist", "visibility", "visibility"),
    ("wishlist_item", "visibility", "visibility"),
    ("wishlist_item", "status", "planstatus"),
)
