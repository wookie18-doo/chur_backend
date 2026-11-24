"""
Redis-backed holding area for uploaded import files.

An ``ImportJob``'s id is the only handle a caller needs. Each file lives
under its own key with a TTL, so concurrent uploads never share state and
a file no worker ever picks up expires on its own. The worker takes the
file with an atomic read-and-delete, so handling it also removes it,
whatever the parse result.
"""

import uuid
from typing import cast

from redis.asyncio import Redis

from app.config.settings import settings
from app.libs.redis.client import RedisClient


class ImportFileStore:
    """Short-lived storage for the raw bytes of uploaded import files."""

    def __init__(self, client: RedisClient) -> None:
        self.client = client

    @staticmethod
    def _key(job_id: uuid.UUID) -> str:
        return f"import_file:{job_id}"

    async def save(self, job_id: uuid.UUID, content: bytes) -> None:
        """
        Park an uploaded file's raw bytes under ``job_id``.

        :param job_id: the import job the file belongs to.
        :param content: the raw uploaded bytes.
        """
        async with Redis(connection_pool=self.client.pool) as redis:
            await redis.set(
                self._key(job_id), content, ex=settings.imports_file_ttl_seconds
            )

    async def pop(self, job_id: uuid.UUID) -> bytes | None:
        """
        Atomically read a saved file and remove it.

        :param job_id: the import job the file belongs to.
        :return: the raw uploaded bytes, or ``None`` if expired or taken.
        """
        async with Redis(connection_pool=self.client.pool) as redis:
            content = await redis.getdel(self._key(job_id))
        return cast(bytes | None, content)
