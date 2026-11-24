"""Wiring for the statement-parsing subsystem."""

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from app.api.dependencies.db import get_db_session
from app.libs.openrouter.client import OpenRouterClient
from app.services.pending_transaction_cache import PendingTransactionCache
from app.services.statement_parse_service import StatementParseService


def get_openrouter_client() -> OpenRouterClient:
    """
    Build the OpenRouter client from settings.

    :return: client instance.
    """
    return OpenRouterClient()


def get_statement_parse_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    llm: OpenRouterClient = Depends(get_openrouter_client),
) -> StatementParseService:
    """
    Build a :class:`~app.services.statement_parse_service.StatementParseService`.

    :param request: current request, for the shared redis client.
    :param session: asynchronous database session.
    :param llm: OpenRouter client.
    :return: service instance.
    """
    cache = PendingTransactionCache(request.app.state.redis_client)
    return StatementParseService(session, cache, llm)
