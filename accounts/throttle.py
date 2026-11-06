"""Simple fixed-window rate limit based on Django's cache."""

from django.core.cache import cache


def client_ip(request) -> str:
    # Behind a reverse proxy this is the proxy's address; proxy headers are
    # handled in milestone 7 (production settings).
    return request.META.get("REMOTE_ADDR", "unknown")


def hit(key: str, limit: int, window_seconds: int) -> bool:
    """Count one request for `key`. Returns False once `limit` is exceeded in the window."""
    cache_key = f"throttle:{key}"
    # add() only sets the value if the key does not exist yet (starts a new window)
    cache.add(cache_key, 0, timeout=window_seconds)
    try:
        count = cache.incr(cache_key)
    except ValueError:  # expired between add() and incr()
        cache.set(cache_key, 1, timeout=window_seconds)
        count = 1
    return count <= limit
