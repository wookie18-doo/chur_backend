"""Background parsing for statement/bill import jobs, triggered on upload."""

import uuid

from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request
from taskiq import TaskiqDepends

from app.api.dependencies.db import get_db_session
from app.services.import_service import ImportService
from app.services.imports.storage import ImportFileStore
from app.tasks.broker import broker


@broker.task
async def process_statement_import(
    job_id: uuid.UUID,
    request: Request = TaskiqDepends(),
    session: AsyncSession = TaskiqDepends(get_db_session),
) -> None:
    """Parse an uploaded bank/broker statement and post its transactions."""
    store = ImportFileStore(request.app.state.redis_client)
    await ImportService(session, store).process_statement_import(job_id)


@broker.task
async def process_bill_import(
    job_id: uuid.UUID,
    account_id: uuid.UUID | None = None,
    request: Request = TaskiqDepends(),
    session: AsyncSession = TaskiqDepends(get_db_session),
) -> None:
    """Parse an uploaded market bill and attach its line items."""
    store = ImportFileStore(request.app.state.redis_client)
    await ImportService(session, store).process_bill_import(job_id, account_id)
