"""Database session/connection dependency for the current request."""

from collections.abc import AsyncGenerator

from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request
from taskiq import TaskiqDepends


async def get_db_session(
    request: Request = TaskiqDepends(),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Create and get database session.

    :param request: current request.
    :yield: database session.
    """
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session
        await session.commit()
