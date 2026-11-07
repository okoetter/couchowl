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
        """Register a response. `json` may also be a function: request -> data or Response."""
        self.routes[path] = (status, json, content, headers or {})

    def add_show(self, details=None, seasons=None):
        """Register a show with its seasons, by default "Dark" (70523).

        Details and the season requests share the path /3/tv/<id>; they differ in
        `append_to_response`. `seasons(language)` returns {number: season} or None
        (default: dark_seasons).
        """
        details = details or load_tmdb_fixture("tv_70523")
        seasons = seasons or dark_seasons

        def respond(request):
            appended = request.url.params.get("append_to_response", "")
            if not appended.startswith("season/"):
                return details
            available = seasons(request.url.params["language"]) or {}
            numbers = [int(key.removeprefix("season/")) for key in appended.split(",")]
            return {
                "id": details["id"],
                **{f"season/{n}": available[n] for n in numbers if n in available},
            }

        self.add(f"/3/tv/{details['id']}", json=respond)

    def add_image(self, size, filename):
        self.add(
            f"/t/p/{size}/{filename}", content=tiny_png(), headers={"Content-Type": "image/png"}
        )

    def handler(self, request):
        self.requests.append(request)
        if request.url.path not in self.routes:
            raise AssertionError(f"Unexpected TMDB request: {request.url}")
        status, json_data, content, headers = self.routes[request.url.path]
        if callable(json_data):
            json_data = json_data(request)
            if isinstance(json_data, httpx.Response):  # e.g. an error for some requests only
                return json_data
        if json_data is not None:
            return httpx.Response(status, json=json_data, headers=headers)
        return httpx.Response(status, content=content, headers=headers)

    def paths(self):
        return [request.url.path for request in self.requests]


def load_tmdb_fixture(name):
    """A saved (shortened) real TMDB response from catalog/tests/fixtures/."""
    return json.loads((TMDB_FIXTURES / f"{name}.json").read_text())


def dark_seasons(language):
    """Seasons of "Dark" as {number: TMDB season}, like TMDB answers in `language`.

    Saved responses exist for de-DE (also used for plain "de") and en-US. Like the real
    TMDB, other languages (e.g. de-AT) only get placeholders: "Episode 1", no description.
    """
    import copy

    name = {"de": "de-DE"}.get(language, language)
    if (TMDB_FIXTURES / f"tv_70523_seasons_{name}.json").exists():
        data = load_tmdb_fixture(f"tv_70523_seasons_{name}")
    else:
        data = copy.deepcopy(load_tmdb_fixture("tv_70523_seasons_de-DE"))
        for key, season in data.items():
            if key.startswith("season/"):
                season.update(name=f"Season {season['season_number']}", overview="")
                for episode in season["episodes"]:
                    episode.update(name=f"Episode {episode['episode_number']}", overview="")
    return {
        int(key.removeprefix("season/")): season
        for key, season in data.items()
        if key.startswith("season/")
    }


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
