from redis.asyncio import Redis

from app.libs.redis.client import RedisClient


class RedisService:
    """
    Business logic for working with Redis.

    Wraps a low-level :class:`~app.libs.redis.client.RedisClient`. Not
    exposed through an example API or GraphQL route -- it's up to the
    caller (your own endpoint, a taskiq task, ...) to obtain the client
    from ``request.app.state.redis_client`` and construct this service.
    """

    def __init__(self, client: RedisClient) -> None:
        self.client = client

    async def get_value(self, key: str) -> str | None:
        """
        Read a value from redis.

        :param key: redis key to read.
        :return: stored value, if any.
        """
        async with Redis(connection_pool=self.client.pool) as redis:
            value = await redis.get(key)
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    async def set_value(self, key: str, value: str) -> None:
        """
        Write a value to redis.

        :param key: redis key to write.
        :param value: value to store.
        """
        async with Redis(connection_pool=self.client.pool) as redis:
            await redis.set(name=key, value=value)
