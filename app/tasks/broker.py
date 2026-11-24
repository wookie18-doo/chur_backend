from typing import Any

import taskiq_fastapi
from taskiq import AsyncBroker, AsyncResultBackend, InMemoryBroker, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.config.settings import settings

result_backend: AsyncResultBackend[Any] = RedisAsyncResultBackend(
    redis_url=str(settings.redis_url.with_path("/1")),
)
# redis-py 8 defaults socket_timeout to 5s, which kills the idle BRPOP.
broker: AsyncBroker = ListQueueBroker(
    str(settings.redis_url.with_path("/1")),
    socket_timeout=None,
).with_result_backend(result_backend)

if settings.environment.lower() == "pytest":
    broker = InMemoryBroker()

taskiq_fastapi.init(
    broker,
    "app.main:app",
)

# Started via `taskiq scheduler app.tasks.broker:scheduler` -- a separate
# process from the worker (see docker-compose.yml's taskiq-scheduler
# service). It only enqueues @broker.task(schedule=[...])-labeled tasks
# on their cron tick; taskiq-worker is what actually executes them.
scheduler = TaskiqScheduler(broker, sources=[LabelScheduleSource(broker)])
