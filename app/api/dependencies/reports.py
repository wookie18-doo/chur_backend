"""Wiring for the reports subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.services.report_service import ReportService


def get_report_service(
    session: AsyncSession = Depends(get_db_session),
) -> ReportService:
    """
    Build a :class:`~app.services.report_service.ReportService`.

    :param session: asynchronous database session.
    :return: service instance.
    """
    return ReportService(session)
