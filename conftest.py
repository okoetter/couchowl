"""Shared pytest fixtures (pytest finds this file automatically)."""

import json
import struct
import zlib
from pathlib import Path

import httpx
import pytest
from django.core.cache import cache

from accounts.models import User
from catalog import tmdb as tmdb_module

TMDB_FIXTURES = Path(__file__).resolve().parent / "catalog" / "tests" / "fixtures"

PASSWORD = "a-Secure-pw-for-tests"  # noqa: S105


@pytest.fixture(autouse=True)
def _clear_cache():
    """Rate limit counters live in the cache; every test starts fresh."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="oliver", email="oliver@example.com", password=PASSWORD, region="DE"
    )


@pytest.fixture
def auth_client(client, user):
    """Test client that is logged in as `user`."""
    client.force_login(user)
    return client


# --- TMDB ------------------------------------------------------------------------------------


class FakeTMDB:
    """Stands in for the TMDB API and image server. Responses are registered per URL path.

    Example: fake_tmdb.add("/3/search/multi", json=load_tmdb_fixture("search_multi"))
    Every request is recorded in `requests`; unknown paths fail the test.
    """

    def __init__(self):
        self.routes = {}
        self.requests = []

    def add(self, path, *, json=None, status=200, content=b"", headers=None):
        self.routes[path] = (status, json, content, headers or {})

    def add_image(self, size, filename):
        self.add(
            f"/t/p/{size}/{filename}", content=tiny_png(), headers={"Content-Type": "image/png"}
        )

    def handler(self, request):
        self.requests.append(request)
        if request.url.path not in self.routes:
            raise AssertionError(f"Unexpected TMDB request: {request.url}")
        status, json_data, content, headers = self.routes[request.url.path]
        if json_data is not None:
            return httpx.Response(status, json=json_data, headers=headers)
        return httpx.Response(status, content=content, headers=headers)

    def paths(self):
        return [request.url.path for request in self.requests]


def load_tmdb_fixture(name):
    """A saved (shortened) real TMDB response from catalog/tests/fixtures/."""
    return json.loads((TMDB_FIXTURES / f"{name}.json").read_text())


def tiny_png(color=(26, 43, 74)):
    """A valid 2x3 PNG image in one color (poster aspect ratio)."""

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + bytes(color) * 2 for _ in range(3))
    header = struct.pack(">IIBBBBB", 2, 3, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


@pytest.fixture(autouse=True)
def fake_tmdb(request, monkeypatch, settings, tmp_path):
    """Tests never talk to the real TMDB (except those marked `live`).

    Every test gets a FakeTMDB; register the responses a test needs on it.
    Posters are cached in a fresh temporary directory per test.
    """
    if request.node.get_closest_marker("live"):
        yield None
        return
    fake = FakeTMDB()
    client = tmdb_module.TMDBClient(
        "test-token", transport=httpx.MockTransport(fake.handler), requests_per_second=0
    )
    monkeypatch.setattr(tmdb_module, "_client", client)
    settings.TMDB_API_TOKEN = "test-token"  # noqa: S105
    settings.POSTER_CACHE_DIR = tmp_path / "posters"
    yield fake
