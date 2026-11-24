from datetime import date
from typing import cast

from fastapi import APIRouter, Depends, Query

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.reports import get_report_service
from app.api.v1.reports.schema import AccountFlowRead, ReportSummaryRead
from app.db.sql.models.users import User
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary", response_model=ReportSummaryRead)
async def read_summary(
    *,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    scope: str = Query("me", pattern="^(me|family)$"),
    group_by_category: bool = Query(False),
    group_by_account: bool = Query(False),
    user: RequestUser = Depends(require_auth),
    report_service: ReportService = Depends(get_report_service),
) -> ReportSummaryRead:
    """
    Compute total income, total spent, and their diff for a period.

    :param date_from: earliest date to include, inclusive.
    :param date_to: latest date to include, inclusive.
    :param scope: ``"me"`` or ``"family"``.
    :param group_by_category: also break spending down by category.
    :param group_by_account: also break both totals down by account.
    :param user: the authenticated user.
    :param report_service: report service.
    :return: the computed summary.
    """
    summary = await report_service.summary(
        cast(User, user.unwrap()),
        date_from=date_from,
        date_to=date_to,
        scope=scope,
        group_by_category=group_by_category,
        group_by_account=group_by_account,
    )
    by_account = None
    if summary.by_account is not None:
        by_account = {
            account_id: AccountFlowRead(income=flow.income, spent=flow.spent)
            for account_id, flow in summary.by_account.items()
        }
    return ReportSummaryRead(
        total_income=summary.total_income,
        total_spent=summary.total_spent,
        diff=summary.diff,
        total_transferred_to_savings=summary.total_transferred_to_savings,
        by_category=summary.by_category,
        by_account=by_account,
    )
