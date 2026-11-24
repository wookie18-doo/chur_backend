import uuid
from decimal import Decimal

from pydantic import BaseModel


class AccountFlowRead(BaseModel):
    """Represents one account's own income/spent totals for a period."""

    income: Decimal
    spent: Decimal


class ReportSummaryRead(BaseModel):
    """Represents the income/spend diff report returned from the API."""

    total_income: Decimal
    total_spent: Decimal
    diff: Decimal
    total_transferred_to_savings: Decimal = Decimal(0)
    by_category: dict[int, Decimal] | None = None
    by_account: dict[uuid.UUID, AccountFlowRead] | None = None
