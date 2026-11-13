import pytest
from django.test import RequestFactory

from accounts.throttle import client_ip


def request(remote="172.18.0.1", forwarded=None):
    meta = {"REMOTE_ADDR": remote}
    if forwarded is not None:
        meta["HTTP_X_FORWARDED_FOR"] = forwarded
    return RequestFactory().get("/", **meta)


@pytest.fixture
def proxies(settings):
    def set_count(count):
        settings.TRUSTED_PROXY_COUNT = count

    return set_count


def test_without_proxy_the_header_is_ignored(proxies):
    proxies(0)

    assert client_ip(request("203.0.113.5", forwarded="198.51.100.1")) == "203.0.113.5"


def test_one_proxy_takes_the_address_it_appended(proxies):
    proxies(1)

    assert client_ip(request(forwarded="203.0.113.5")) == "203.0.113.5"


def test_forged_entries_on_the_left_are_ignored(proxies):
    proxies(1)

    assert client_ip(request(forwarded="10.0.0.1, 1.2.3.4,203.0.113.5")) == "203.0.113.5"


def test_two_proxies(proxies):
    # client -> outer proxy (appends client) -> inner proxy (appends outer) -> Couch Owl
    proxies(2)

    forwarded = "10.0.0.1, 203.0.113.5, 192.0.2.10"

    assert client_ip(request(forwarded=forwarded)) == "203.0.113.5"


def test_request_that_skipped_the_proxy_uses_remote_addr(proxies):
    # e.g. the container's healthcheck on 127.0.0.1
    proxies(1)

    assert client_ip(request("127.0.0.1")) == "127.0.0.1"


@pytest.mark.parametrize(
    ("forwarded", "expected"),
    [
        ("2001:DB8:0:0::7", "2001:db8::7"),  # canonical IPv6
        ("[2001:db8::7]:4711", "2001:db8::7"),  # with port
        ("203.0.113.5:4711", "203.0.113.5"),
        ("::ffff:203.0.113.5", "203.0.113.5"),  # IPv4 in IPv6 form
    ],
)
def test_addresses_are_normalized(proxies, forwarded, expected):
    proxies(1)

    assert client_ip(request(forwarded=forwarded)) == expected


def test_garbage_falls_back_to_remote_addr(proxies):
    proxies(1)

    assert client_ip(request(forwarded="unknown")) == "172.18.0.1"
