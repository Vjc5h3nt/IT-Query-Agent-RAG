"""Simple in-memory response cache with TTL."""
import time
from typing import Any, Optional

_store: dict = {}


def get(key: str, namespace: str = "default") -> Optional[Any]:
    namespaced_key = f"{namespace}:{key}"
    entry = _store.get(namespaced_key)
    if entry and time.time() < entry["expires"]:
        return entry["value"]
    if entry:
        del _store[namespaced_key]
    return None


def set(key: str, value: Any, ttl: int = 300, namespace: str = "default"):
    from app.config import settings
    namespaced_key = f"{namespace}:{key}"
    max_size = settings.cache_max_size
    if len(_store) >= max_size:
        # evict oldest
        oldest = min(_store, key=lambda k: _store[k]["expires"])
        del _store[oldest]
    _store[namespaced_key] = {"value": value, "expires": time.time() + ttl}


def invalidate(key: str):
    _store.pop(key, None)


def stats() -> dict:
    now = time.time()
    active = sum(1 for v in _store.values() if now < v["expires"])
    return {"total_keys": len(_store), "active_keys": active}
# Cache module
