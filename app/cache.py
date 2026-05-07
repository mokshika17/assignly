# app/cache.py
import json
import redis
from app.config import settings

_client: redis.Redis | None = None

def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def cache_get(key: str):
    try:
        val = get_redis().get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


def cache_set(key: str, value, ttl: int):
    try:
        get_redis().setex(key, ttl, json.dumps(value))
    except Exception:
        pass


def cache_delete(*keys: str):
    try:
        get_redis().delete(*keys)
    except Exception:
        pass