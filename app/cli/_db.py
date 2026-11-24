"""One-shot async db session for CLI commands, outside any HTTP request."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.sql.db import create_db_engine, create_session_factory


@asynccontextmanager
async def cli_session() -> AsyncIterator[AsyncSession]:
    """
    Open a db session for the lifetime of one CLI command.

    Same commit-on-success shape as ``app.api.dependencies.db.
    get_db_session``, but owns and disposes its own engine instead of
    reusing ``app.state.db_engine`` -- a CLI invocation has no app state.

    :yield: a session, committed if the command body doesn't raise.
    """
    engine = create_db_engine()
    try:
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            yield session
            await session.commit()
    finally:
        await engine.dispose()
