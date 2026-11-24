import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlmodel.ext.asyncio.session import AsyncSession

from app.dal.income_query import IncomeQuery
from app.dal.spent_query import SpentQuery
from app.dal.transfer_query import TransferQuery
from app.db.sql.models.users import User
from app.services.visibility_service import VisibilityService


@dataclass
class AccountFlow:
    """One account's own income/spent totals for a period."""

    income: Decimal
    spent: Decimal


@dataclass
class ReportSummary:
    """The result of :meth:`ReportService.summary`."""

    total_income: Decimal
    total_spent: Decimal
    diff: Decimal
    total_transferred_to_savings: Decimal = Decimal(0)
    by_category: dict[int, Decimal] | None = None
    by_account: dict[uuid.UUID, AccountFlow] | None = None


class ReportService:
    """
    Business logic for the income/spend diff report.

    Builds its own :class:`~app.dal.spent_query.SpentQuery` and
    :class:`~app.dal.income_query.IncomeQuery` from the db session it's
    given -- callers never construct a query object themselves.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.spents = SpentQuery(session)
        self.incomes = IncomeQuery(session)
        self.transfers = TransferQuery(session)

    async def summary(
        self,
        actor: User,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        scope: str = "me",
        group_by_category: bool = False,
        group_by_account: bool = False,
    ) -> ReportSummary:
        """
        Compute total income, total spent, and their diff for a period.

        :param actor: user requesting the report.
        :param date_from: earliest date to include, inclusive.
        :param date_to: latest date to include, inclusive.
        :param scope: ``"me"`` or ``"family"``.
        :param group_by_category: also break spending down by category.
        :param group_by_account: also break both totals down by account.
        :return: the computed summary.
        """
        visibility_service = VisibilityService(actor.id, self.session)
        owner_ids = await visibility_service.visible_owner_ids(scope=scope)

        total_spent = await self.spents.sum_for_range(
            actor.id, owner_ids, date_from=date_from, date_to=date_to
        )
        total_income = await self.incomes.sum_for_range(
            actor.id, owner_ids, date_from=date_from, date_to=date_to
        )

        total_transferred_to_savings = await self.transfers.sum_to_savings_accounts(
            actor.id, owner_ids, date_from=date_from, date_to=date_to
        )

        by_category = None
        if group_by_category:
            by_category = await self.spents.sum_by_category(
                actor.id, owner_ids, date_from=date_from, date_to=date_to
            )

        by_account = None
        if group_by_account:
            spent_by_account = await self.spents.sum_by_account(
                actor.id, owner_ids, date_from=date_from, date_to=date_to
            )
            income_by_account = await self.incomes.sum_by_account(
                actor.id, owner_ids, date_from=date_from, date_to=date_to
            )
            account_ids = set(spent_by_account) | set(income_by_account)
            by_account = {
                account_id: AccountFlow(
                    income=income_by_account.get(account_id, Decimal(0)),
                    spent=spent_by_account.get(account_id, Decimal(0)),
                )
                for account_id in account_ids
            }

        return ReportSummary(
            total_income=total_income,
            total_spent=total_spent,
            diff=total_income - total_spent,
            total_transferred_to_savings=total_transferred_to_savings,
            by_category=by_category,
            by_account=by_account,
        )
