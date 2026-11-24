import json
import time
import uuid
from typing import Any

from redis.asyncio import Redis

from app.config.settings import settings
from app.libs.redis.client import RedisClient


class PendingTransactionCache:
    """
    Redis-backed holding area for parsed-but-unsaved statement transactions.

    Each transaction lives under its own key with a TTL, so a client that
    disconnects mid-review can fetch what is left later; the per-user index
    only exists to find those keys without a ``SCAN``, and is pruned of
    expired members whenever it is read.
    """

    def __init__(self, client: RedisClient) -> None:
        self.client = client

    @staticmethod
    def _tx_key(user_id: uuid.UUID, tx_id: str) -> str:
        return f"stmt_tx:{user_id}:{tx_id}"

    @staticmethod
    def _index_key(user_id: uuid.UUID) -> str:
        return f"stmt_tx_idx:{user_id}"

    async def add_many(
        self, user_id: uuid.UUID, transactions: list[dict[str, Any]]
    ) -> None:
        """
        Store transactions, each with its own TTL.

        :param user_id: owner of the transactions.
        :param transactions: JSON-serialisable dicts, each with an ``id``.
        """
        if not transactions:
            return
        ttl = settings.statement_parsing_cache_ttl_seconds
        index_key = self._index_key(user_id)
        now = time.time()
        async with Redis(connection_pool=self.client.pool) as redis:
            pipe = redis.pipeline()
            for offset, tx in enumerate(transactions):
                pipe.set(self._tx_key(user_id, tx["id"]), json.dumps(tx), ex=ttl)
                # Distinct scores keep a batch in its original row order.
                pipe.zadd(index_key, {tx["id"]: now + offset * 1e-6})
            pipe.expire(index_key, ttl)
            await pipe.execute()

    async def list(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """
        Fetch every still-pending transaction of a user.

        :param user_id: owner of the transactions.
        :return: pending transactions, oldest upload first.
        """
        index_key = self._index_key(user_id)
        async with Redis(connection_pool=self.client.pool) as redis:
            raw = await redis.zrange(index_key, 0, -1)
            members = [m.decode() if isinstance(m, bytes) else str(m) for m in raw]
            if not members:
                return []
            values = await redis.mget(self._tx_key(user_id, m) for m in members)
            expired = [m for m, v in zip(members, values, strict=True) if v is None]
            if expired:
                await redis.zrem(index_key, *expired)
        return [json.loads(v) for v in values if v is not None]

    async def get(self, user_id: uuid.UUID, tx_id: str) -> dict[str, Any] | None:
        """
        Fetch one pending transaction.

        :param user_id: owner of the transaction.
        :param tx_id: transaction id.
        :return: the transaction, or ``None`` if unknown or expired.
        """
        async with Redis(connection_pool=self.client.pool) as redis:
            value = await redis.get(self._tx_key(user_id, tx_id))
        return None if value is None else json.loads(value)

    async def remove(self, user_id: uuid.UUID, tx_id: str) -> bool:
        """
        Drop one pending transaction.

        :param user_id: owner of the transaction.
        :param tx_id: transaction id.
        :return: whether it was still pending.
        """
        async with Redis(connection_pool=self.client.pool) as redis:
            pipe = redis.pipeline()
            pipe.delete(self._tx_key(user_id, tx_id))
            pipe.zrem(self._index_key(user_id), tx_id)
            deleted, _ = await pipe.execute()
        return bool(deleted)
