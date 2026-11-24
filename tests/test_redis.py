import uuid

from redis.asyncio import Redis

from app.libs.redis.client import RedisClient
from app.services.redis_service import RedisService


async def test_setting_value(
    test_redis_client: RedisClient,
) -> None:
    """
    Tests that you can set value in redis.

    RedisService isn't exposed through an API or GraphQL route -- see
    app.services.redis_service -- so this exercises the service directly.

    :param test_redis_client: connected redis client.
    """
    test_key = uuid.uuid4().hex
    test_val = uuid.uuid4().hex

    await RedisService(test_redis_client).set_value(key=test_key, value=test_val)

    async with Redis(connection_pool=test_redis_client.pool) as redis:
        actual_value = await redis.get(test_key)
    assert isinstance(actual_value, bytes)
    assert actual_value.decode() == test_val


async def test_getting_value(
    test_redis_client: RedisClient,
) -> None:
    """
    Tests that you can get value from redis by key.

    :param test_redis_client: connected redis client.
    """
    test_key = uuid.uuid4().hex
    test_val = uuid.uuid4().hex
    async with Redis(connection_pool=test_redis_client.pool) as redis:
        await redis.set(test_key, test_val)

    actual_value = await RedisService(test_redis_client).get_value(test_key)
    assert actual_value == test_val
