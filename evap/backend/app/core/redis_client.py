from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Optional

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool

from app.core.config import settings

# ---------------------------------------------------------------------------
# Connection pool (created once at startup)
# ---------------------------------------------------------------------------
_pool: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=20,
            decode_responses=True,
        )
    return _pool


def get_redis_client() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=get_pool())


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------
async def get_cache(key: str) -> Optional[Any]:
    """Return deserialized value or None if key does not exist."""
    client = get_redis_client()
    value = await client.get(key)
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


async def set_cache(key: str, value: Any, ttl: int = 300) -> None:
    """Serialize and store value with TTL (seconds)."""
    client = get_redis_client()
    serialized = json.dumps(value, default=str)
    await client.set(key, serialized, ex=ttl)


async def delete_cache(key: str) -> None:
    client = get_redis_client()
    await client.delete(key)


async def publish(channel: str, message: Any) -> None:
    """Publish a message to a Redis pub/sub channel."""
    client = get_redis_client()
    payload = json.dumps(message, default=str)
    await client.publish(channel, payload)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
async def init_redis() -> None:
    """Verify Redis connectivity at startup."""
    client = get_redis_client()
    await client.ping()


async def close_redis() -> None:
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None
