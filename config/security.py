"""Derive host, cookie and HTTPS settings from SITE_URL and TRUSTED_PROXY_COUNT.

A pure function (like config/mail.py) so the rules can be tested: Django reads
settings only once, at import time.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

# One year: the usual value. Browsers then refuse plain http for this host for a year.
DEFAULT_HSTS_SECONDS = 365 * 24 * 3600


@dataclass(frozen=True)
class SecuritySettings:
    site_url: str  # without trailing slash, "" if not configured
    allowed_hosts: list[str]
    csrf_trusted_origins: list[str]
    https: bool
    hsts_seconds: int
    # Only set behind a trusted proxy: otherwise any client could claim "https"
    proxy_ssl_header: tuple[str, str] | None


def security_settings(
    site_url: str, proxy_count: int, hsts_seconds: int | None = None
) -> SecuritySettings:
    """Settings for Couch Owl reachable at `site_url` behind `proxy_count` reverse proxies.

    `hsts_seconds=None` means the default (one year, only with https).
    """
    if proxy_count < 0:
        raise ImproperlyConfigured("TRUSTED_PROXY_COUNT must be 0 or more.")
    proxy_ssl_header = ("HTTP_X_FORWARDED_PROTO", "https") if proxy_count else None

    if not site_url:
        return SecuritySettings("", [], [], False, 0, proxy_ssl_header)

    parts = urlsplit(site_url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ImproperlyConfigured(
            f"SITE_URL must look like https://couchowl.example.com, not {site_url!r}."
        )
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ImproperlyConfigured(
            "SITE_URL must not contain a path: Couch Owl needs its own (sub)domain."
        )
    https = parts.scheme == "https"
    if https and not proxy_count:
        # Couch Owl itself only speaks http; https always comes from a reverse proxy
        raise ImproperlyConfigured(
            "SITE_URL uses https, so Couch Owl runs behind a reverse proxy: "
            "set TRUSTED_PROXY_COUNT (usually 1)."
        )

    host = parts.hostname  # lowercase, without port and IPv6 brackets
    origin = f"{parts.scheme}://{parts.netloc.lower()}"
    if hsts_seconds is None:
        hsts_seconds = DEFAULT_HSTS_SECONDS
    return SecuritySettings(
        site_url=origin,
        allowed_hosts=[f"[{host}]" if ":" in host else host],
        csrf_trusted_origins=[origin],
        https=https,
        hsts_seconds=hsts_seconds if https else 0,
        proxy_ssl_header=proxy_ssl_header,
    )
