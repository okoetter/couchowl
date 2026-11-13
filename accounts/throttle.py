"""Client IP address behind reverse proxies, and a simple rate limit based on Django's cache."""

import ipaddress

from django.conf import settings
from django.core.cache import cache


def client_ip(request) -> str:
    """The address of the client, also behind TRUSTED_PROXY_COUNT reverse proxies.

    Used for watchit's rate limits and by django-axes (AXES_CLIENT_IP_CALLABLE).

    Each proxy appends the address it received the request from to X-Forwarded-For, the
    nearest proxy is REMOTE_ADDR. So with n trusted proxies, the client is the n-th entry
    from the right; anything further left was sent by the client and could be forged.
    Without trusted proxies the header is ignored for the same reason.
    """
    remote = request.META.get("REMOTE_ADDR", "")
    proxies = settings.TRUSTED_PROXY_COUNT
    if proxies:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        chain = [part.strip() for part in forwarded.split(",") if part.strip()]
        chain.append(remote)
        # Fewer entries than proxies: the request didn't pass all of them (e.g. the
        # container's own healthcheck), so REMOTE_ADDR is the client
        if len(chain) > proxies and (address := _normalize(chain[-1 - proxies])):
            return address
    return _normalize(remote) or "unknown"


def _normalize(value: str) -> str | None:
    """A valid IPv4/IPv6 address in canonical form, or None.

    Some proxies add a port ("203.0.113.5:4711", "[2001:db8::1]:4711"); IPv4 addresses
    in IPv6 form ("::ffff:203.0.113.5") count as IPv4, so one client has one address.
    """
    if value.startswith("["):  # [IPv6]:port
        value = value[1:].partition("]")[0]
    elif value.count(":") == 1:  # IPv4:port
        value = value.partition(":")[0]
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address)


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
