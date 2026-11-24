import enum


class Visibility(enum.StrEnum):
    """Who besides the owner can see a record."""

    PRIVATE = "private"
    FAMILY = "family"


class FamilyRole(enum.StrEnum):
    """A member's standing within their family."""

    OWNER = "owner"
    MEMBER = "member"


class CategoryKind(enum.StrEnum):
    """Whether a category applies to spents or incomes."""

    EXPENSE = "expense"
    INCOME = "income"


class CategoryColor(enum.StrEnum):
    """The fixed color palette offered when creating a category."""

    CLAY = "clay"
    BLUE = "blue"
    VIOLET = "violet"
    OCHRE = "ochre"
    TEAL = "teal"


class PlanStatus(enum.StrEnum):
    """Lifecycle of a wishlist item or planned income."""

    PLANNED = "planned"
    REALISED = "realised"


class RecurrenceFrequency(enum.StrEnum):
    """How often a recurring transaction repeats."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class AccountKind(enum.StrEnum):
    """What kind of money source an account represents."""

    BANK = "bank"
    CASH = "cash"
    CARD = "card"
    BROKER = "broker"
    JAR = "jar"
    OTHER = "other"


class ImportStatus(enum.StrEnum):
    """Lifecycle of a statement/bill import job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportedTransactionStatus(enum.StrEnum):
    """What happened to one parsed row from an import job."""

    IMPORTED = "imported"
    DUPLICATE_SKIPPED = "duplicate_skipped"
    FAILED = "failed"
