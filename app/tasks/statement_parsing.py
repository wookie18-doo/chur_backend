"""Background LLM parsing of uploaded statements."""

import base64
import uuid

from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request
from taskiq import TaskiqDepends

from app.api.dependencies.db import get_db_session
from app.libs.openrouter.client import OpenRouterClient
from app.services.pending_transaction_cache import PendingTransactionCache
from app.services.statement_parse_service import StatementParseService
from app.tasks.broker import broker


@broker.task
async def process_statement_parse(
    job_id: uuid.UUID,
    files: list[tuple[str, str]],
    request: Request = TaskiqDepends(),
    session: AsyncSession = TaskiqDepends(get_db_session),
) -> None:
    """
    Parse an uploaded statement and cache its transactions.

    :param job_id: job created when the files were uploaded.
    :param files: ``(filename, base64 content)`` pairs -- base64 because task
        arguments travel as JSON; the bytes are held in memory only.
    :param request: the app's request stand-in, for the shared redis client.
    :param session: database session.
    """
    service = StatementParseService(
        session,
        PendingTransactionCache(request.app.state.redis_client),
        OpenRouterClient(),
    )
    await service.process(
        job_id, [(name, base64.b64decode(data)) for name, data in files]
    )
