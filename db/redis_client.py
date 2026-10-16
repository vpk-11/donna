import os
import redis

_REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
_REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

_sync_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = redis.Redis(host=_REDIS_HOST, port=_REDIS_PORT, decode_responses=True)
    return _sync_client


def ping_redis() -> bool:
    try:
        return get_redis().ping()
    except Exception:
        return False
