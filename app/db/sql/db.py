from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config.settings import settings


def create_db_engine() -> AsyncEngine:
    """
    Create the SQLAlchemy engine for this application.

    :return: configured async engine.
    """
    return create_async_engine(str(settings.db_url), echo=settings.db_echo)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Build a session factory bound to the given engine.

    :param engine: engine to bind sessions to.
    :return: session factory.
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
