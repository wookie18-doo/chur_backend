from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.dependencies.db import get_db_session
from app.config.settings import settings
from app.db.sql.seed_data import (
    BUILTIN_CATEGORIES,
    BUILTIN_CURRENCIES,
    BUILTIN_STATEMENT_SOURCES,
)
from app.libs.redis.client import RedisClient
from app.main import app
from app.services.imports.storage import ImportFileStore


async def create_database() -> None:
    """Create a database for tests."""
    db_url = make_url(str(settings.db_url.with_path("/postgres")))
    engine = create_async_engine(db_url, isolation_level="AUTOCOMMIT")

    async with engine.connect() as conn:
        database_existance = await conn.execute(
            text(
                f"SELECT 1 FROM pg_database WHERE datname='{settings.db_base}'",  # noqa: S608
            )
        )
        database_exists = database_existance.scalar() == 1

    if database_exists:
        await drop_database()

    async with engine.connect() as conn:
        await conn.execute(
            text(
                f'CREATE DATABASE "{settings.db_base}" ENCODING "utf8" TEMPLATE template1',  # noqa: E501
            )
        )


async def drop_database() -> None:
    """Drop the test database."""
    db_url = make_url(str(settings.db_url.with_path("/postgres")))
    engine = create_async_engine(db_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        disc_users = (
            "SELECT pg_terminate_backend(pg_stat_activity.pid) "  # noqa: S608
            "FROM pg_stat_activity "
            f"WHERE pg_stat_activity.datname = '{settings.db_base}' "
            "AND pid <> pg_backend_pid();"
        )
        await conn.execute(text(disc_users))
        await conn.execute(text(f'DROP DATABASE "{settings.db_base}"'))


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """
    Backend for anyio pytest plugin.

    :return: backend name.
    """
    return "asyncio"


@pytest.fixture(scope="session")
async def _engine(anyio_backend: Any) -> AsyncGenerator[AsyncEngine, None]:
    """
    Create engine and databases.

    :yield: new engine.
    """
    from app.db.sql.meta import meta
    from app.db.sql.models import load_all_models

    load_all_models()

    await create_database()

    engine = create_async_engine(str(settings.db_url))
    async with engine.begin() as conn:
        await conn.run_sync(meta.create_all)
        # Schema is built straight from models here, not by running the
        # migrations -- so the data migration's bulk_insert never runs and
        # has to be replicated for tests to see the built-in categories.
        category_table = meta.tables["category"]
        await conn.execute(category_table.insert(), BUILTIN_CATEGORIES)
        await conn.execute(meta.tables["currency"].insert(), BUILTIN_CURRENCIES)
        await conn.execute(
            meta.tables["statement_source"].insert(), BUILTIN_STATEMENT_SOURCES
        )

    try:
        yield engine
    finally:
        await engine.dispose()
        await drop_database()


@pytest.fixture
async def dbsession(
    _engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get session to database.

    Fixture that returns a SQLAlchemy session with a SAVEPOINT, and the rollback to it
    after the test completes.

    :param _engine: current engine.
    :yields: async session.
    """
    connection = await _engine.connect()
    trans = await connection.begin()

    session_maker = async_sessionmaker(
        connection,
        class_=AsyncSession,
        expire_on_commit=False,
        # Default "conditional_savepoint" still shares the outer `trans`
        # directly instead of nesting -- a session.rollback() (e.g. after a
        # caught IntegrityError) then finishes `trans` itself, and this
        # fixture's own rollback below fails on the "already deassociated"
        # transaction. Force an actual SAVEPOINT so mid-test rollbacks stay
        # scoped to the session.
        join_transaction_mode="create_savepoint",
    )
    session = session_maker()

    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await connection.close()


@pytest.fixture
async def test_redis_client() -> AsyncGenerator[RedisClient, None]:
    """
    Get instance of a connected redis client.

    :yield: connected redis client.
    """
    client = RedisClient(str(settings.redis_url))
    await client.connect()

    yield client

    await client.disconnect()


class _StaticSessionFactory:
    """
    Ties ``app.state.db_session_factory`` to the test's transactional session.

    ``app.api.middlewares.auth.AuthMiddleware`` reads
    ``app.state.db_session_factory`` directly instead of going through
    FastAPI's dependency injection, so it doesn't see the ``get_db_session``
    override above on its own -- without this, a user created earlier in a
    test wouldn't be visible when the middleware looks it up, since it'd be
    querying a brand new, unrelated connection instead of the test's
    SAVEPOINT-scoped one.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> "_StaticSessionFactory":
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@pytest.fixture
def fastapi_app(
    dbsession: AsyncSession,
    test_redis_client: RedisClient,
) -> FastAPI:
    """
    Fixture for creating FastAPI app.

    :return: fastapi app with mocked dependencies.
    """
    application = app
    application.dependency_overrides[get_db_session] = lambda: dbsession
    application.state.db_session_factory = _StaticSessionFactory(dbsession)
    application.state.redis_client = test_redis_client
    return application


@pytest.fixture
async def client(
    fastapi_app: FastAPI, anyio_backend: Any
) -> AsyncGenerator[AsyncClient, None]:
    """
    Fixture that creates client for requesting server.

    :param fastapi_app: the application.
    :yield: client for the app.
    """
    async with AsyncClient(
        transport=ASGITransport(fastapi_app), base_url="http://test", timeout=2.0
    ) as ac:
        yield ac


@pytest.fixture
def import_file_store(test_redis_client: RedisClient) -> ImportFileStore:
    """
    Build the redis-backed store for uploaded import files.

    :param test_redis_client: connected redis client.
    :return: the store.
    """
    return ImportFileStore(test_redis_client)
