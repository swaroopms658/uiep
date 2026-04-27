import json
import logging
from typing import Any, Optional
from config import settings

logger = logging.getLogger(__name__)

_redis_client = None


def get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            _redis_client.ping()
        except Exception as exc:
            logger.warning("Redis unavailable, caching disabled: %s", exc)
            _redis_client = None
    return _redis_client


def cache_get(key: str) -> Optional[Any]:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as exc:
        logger.warning("Cache get error for key %s: %s", key, exc)
        return None


def cache_set(key: str, value: Any, ttl: int = settings.CACHE_TTL_SECONDS) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.setex(key, ttl, json.dumps(value))
    except Exception as exc:
        logger.warning("Cache set error for key %s: %s", key, exc)


def cache_delete(key: str) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.delete(key)
    except Exception as exc:
        logger.warning("Cache delete error for key %s: %s", key, exc)


def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching a glob pattern (e.g. 'dashboard:user_id:*')."""
    client = get_redis()
    if client is None:
        return
    try:
        keys = client.keys(pattern)
        if keys:
            client.delete(*keys)
    except Exception as exc:
        logger.warning("Cache delete_pattern error for %s: %s", pattern, exc)
