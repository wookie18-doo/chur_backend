from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator.instrumentation import (
    PrometheusFastApiInstrumentator,
)

from app.config.settings import settings
from app.db.sql.db import create_db_engine, create_session_factory
from app.libs.redis.client import RedisClient
from app.services.redis_service import RedisService
from app.tasks.broker import broker


def setup_prometheus(app: FastAPI) -> None:  # pragma: no cover
    """
    Enables prometheus integration.

    :param app: current application.
    """
    PrometheusFastApiInstrumentator(should_group_status_codes=False).instrument(
        app,
    ).expose(app, should_gzip=True, name="prometheus_metrics")


@asynccontextmanager
async def lifespan_setup(
    app: FastAPI,
) -> AsyncGenerator[None, None]:  # pragma: no cover
    """
    Actions to run on application startup.

    This function uses fastAPI app to store data
    in the state, such as db_engine.

    :param app: the fastAPI application.
    :return: function that actually performs actions.
    """

    app.middleware_stack = None
    if not broker.is_worker_process:
        await broker.startup()
    app.state.db_engine = create_db_engine()
    app.state.db_session_factory = create_session_factory(app.state.db_engine)
    app.state.redis_client = RedisClient(str(settings.redis_url))
    await app.state.redis_client.connect()
    app.state.redis_service = RedisService(app.state.redis_client)
    setup_prometheus(app)
    app.middleware_stack = app.build_middleware_stack()

    yield
    if not broker.is_worker_process:
        await broker.shutdown()
    await app.state.db_engine.dispose()

    await app.state.redis_client.disconnect()
