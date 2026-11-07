"""Checks against the real TMDB API: detect changes in TMDB's responses.

Skipped by default. Run manually with a token in .env:
    uv run pytest -m live
"""

import pytest
from django.conf import settings

from catalog import services, tmdb

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not settings.TMDB_API_TOKEN, reason="TMDB_API_TOKEN not set"),
]


@pytest.fixture(autouse=True)
def fresh_client(monkeypatch):
    """A real client with the token from .env (not the fake one from other tests)."""
    monkeypatch.setattr(tmdb, "_client", None)


def test_search_finds_movies_and_shows():
    results = services.search("Dark", "de-DE")

    assert any(r.media_type == "tv" and r.tmdb_id == 70523 for r in results)
    assert all(r.media_type in ("movie", "tv") for r in results)


@pytest.mark.django_db
def test_details_with_language_fallback():
    # TMDB has no Austrian description of "Dark"; the German one must be used
    result = services.get_title("tv", 70523, "de-AT")

    assert result.title.original_title == "Dark"
    assert "Kind" in result.overview


def test_poster_download():
    content, content_type = tmdb.get_client().image("w92", "gw8ZlIXEg6SIx3FgMEQqmBkPYKV.jpg")

    assert content_type == "image/jpeg"
    assert len(content) > 1000
