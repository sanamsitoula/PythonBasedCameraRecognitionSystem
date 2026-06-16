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
    """Return deserialized value or None if key does not exist / Redis is down."""
    try:
        client = get_redis_client()
        value = await client.get(key)
        if value is None:
            return None
        return json.loads(value)
    except Exception:
        return None


async def set_cache(key: str, value: Any, ttl: int = 300) -> None:
    """Serialize and store value with TTL. No-op if Redis is down."""
    try:
        client = get_redis_client()
        serialized = json.dumps(value, default=str)
        await client.set(key, serialized, ex=ttl)
    except Exception:
        pass


async def delete_cache(key: str) -> None:
    try:
        client = get_redis_client()
        await client.delete(key)
    except Exception:
        pass


async def publish(channel: str, message: Any) -> None:
    """Publish to a Redis pub/sub channel. No-op if Redis is down."""
    try:
        client = get_redis_client()
        payload = json.dumps(message, default=str)
        await client.publish(channel, payload)
    except Exception:
        pass


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
    """Verify Redis connectivity at startup. Non-fatal — app runs without Redis."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        client = get_redis_client()
        await client.ping()
        logger.info("Redis connected at %s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning(
            "Redis not available (%s). Caching and pub/sub disabled. "
            "Install Redis or set REDIS_URL to suppress this warning.",
            exc,
        )


async def close_redis() -> None:
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None
