from redis.asyncio import ConnectionPool


class RedisClient:
    """
    Low-level wrapper around a Redis connection pool.

    Owns the pool's lifecycle (:meth:`connect`/:meth:`disconnect`) so it can
    be built once at startup, stored on ``app.state``, and handed to
    :class:`~app.services.redis_service.RedisService`.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self._pool: ConnectionPool | None = None

    async def connect(self) -> None:
        """Create the connection pool."""
        self._pool = ConnectionPool.from_url(self.url)

    async def disconnect(self) -> None:
        """Close the connection pool, if one was created."""
        if self._pool is not None:
            await self._pool.disconnect()

    @property
    def pool(self) -> ConnectionPool:
        """
        The active connection pool.

        :raises RuntimeError: if :meth:`connect` hasn't been called yet.
        :return: connection pool.
        """
        if self._pool is None:
            raise RuntimeError("RedisClient is not connected. Call connect() first.")
        return self._pool
