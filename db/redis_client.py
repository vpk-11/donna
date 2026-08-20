import os
import redis
import redis.asyncio as aioredis

_REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
_REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

_sync_client: redis.Redis | None = None
_async_client: aioredis.Redis | None = None


def get_redis() -> redis.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = redis.Redis(host=_REDIS_HOST, port=_REDIS_PORT, decode_responses=True)
    return _sync_client


# Not called yet — reserved for V3's async pub/sub dispatch work.
def get_async_redis() -> aioredis.Redis:
    global _async_client
    if _async_client is None:
        _async_client = aioredis.Redis(host=_REDIS_HOST, port=_REDIS_PORT, decode_responses=True)
    return _async_client


def ping_redis() -> bool:
    try:
        return get_redis().ping()
    except Exception:
        return False
