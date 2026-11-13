import pytest
from django.core.exceptions import ImproperlyConfigured

from config.security import DEFAULT_HSTS_SECONDS, security_settings


def test_nothing_configured():
    security = security_settings("", 0)

    assert security.allowed_hosts == []
    assert security.csrf_trusted_origins == []
    assert not security.https
    assert security.hsts_seconds == 0
    assert security.proxy_ssl_header is None


def test_https_behind_a_proxy():
    security = security_settings("https://Watchit.Example.com/", 1)

    assert security.site_url == "https://watchit.example.com"
    assert security.allowed_hosts == ["watchit.example.com"]
    assert security.csrf_trusted_origins == ["https://watchit.example.com"]
    assert security.https
    assert security.hsts_seconds == DEFAULT_HSTS_SECONDS
    assert security.proxy_ssl_header == ("HTTP_X_FORWARDED_PROTO", "https")


def test_hsts_can_be_turned_off():
    # e.g. because the reverse proxy already sends the header
    assert security_settings("https://watchit.example.com", 1, hsts_seconds=0).hsts_seconds == 0


def test_plain_http_in_the_home_network():
    security = security_settings("http://nas.local:8000", 0)

    assert security.allowed_hosts == ["nas.local"]
    assert security.csrf_trusted_origins == ["http://nas.local:8000"]
    assert not security.https
    assert security.hsts_seconds == 0


def test_ipv6_address_as_host():
    security = security_settings("http://[2001:db8::7]:8000", 0)

    assert security.allowed_hosts == ["[2001:db8::7]"]
    assert security.csrf_trusted_origins == ["http://[2001:db8::7]:8000"]


def test_proxy_without_site_url_still_trusts_the_proto_header():
    assert security_settings("", 1).proxy_ssl_header == ("HTTP_X_FORWARDED_PROTO", "https")


@pytest.mark.parametrize(
    ("site_url", "proxies", "message"),
    [
        ("watchit.example.com", 1, "must look like"),
        ("ftp://watchit.example.com", 1, "must look like"),
        ("https://example.com/watchit", 1, "must not contain a path"),
        ("https://watchit.example.com", 0, "TRUSTED_PROXY_COUNT"),
        ("", -1, "TRUSTED_PROXY_COUNT"),
    ],
)
def test_invalid_configuration(site_url, proxies, message):
    with pytest.raises(ImproperlyConfigured, match=message):
        security_settings(site_url, proxies)
