"""
Fixed seed rows inserted by data migrations.

Single source of truth for rows a migration bulk-inserts, so the migration
script and anything else that needs to know what got seeded (e.g. tests
building the schema straight from models, bypassing migrations) can't drift
apart.
"""

BUILTIN_CATEGORIES: list[dict[str, str | None]] = [
    {"name": "Groceries", "kind": "expense", "owner_id": None, "color": "teal"},
    {"name": "Transport", "kind": "expense", "owner_id": None, "color": "blue"},
    {"name": "Housing", "kind": "expense", "owner_id": None, "color": "clay"},
    {"name": "Health", "kind": "expense", "owner_id": None, "color": "ochre"},
    {"name": "Entertainment", "kind": "expense", "owner_id": None, "color": "violet"},
    {"name": "Other", "kind": "expense", "owner_id": None, "color": None},
    {"name": "Uncategorized", "kind": "expense", "owner_id": None, "color": None},
    {"name": "Salary", "kind": "income", "owner_id": None, "color": None},
    {"name": "Other", "kind": "income", "owner_id": None, "color": None},
    {"name": "Uncategorized", "kind": "income", "owner_id": None, "color": None},
]

BUILTIN_STATEMENT_SOURCES: list[dict[str, str]] = [
    {"name": "Wise"},
    {"name": "Bunq"},
    {"name": "Dukascopy"},
    {"name": "Deblock"},
    {"name": "Market bill"},
    {"name": "Revolut"},
]

BUILTIN_CURRENCIES: list[dict[str, str | bool]] = [
    {"code": "EUR", "name": "Euro", "is_active": True},
    {"code": "USD", "name": "US Dollar", "is_active": True},
    {"code": "GBP", "name": "British Pound", "is_active": True},
    {"code": "CHF", "name": "Swiss Franc", "is_active": True},
]
