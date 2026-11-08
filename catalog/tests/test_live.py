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


@pytest.mark.django_db
def test_episodes_with_language_fallback():
    # TMDB only has placeholders ("Folge 1") for "de-AT"; the German texts must be used
    from catalog.models import EpisodeTranslation

    show = services.get_title("tv", 70523, "de-AT").title

    first = EpisodeTranslation.objects.get(
        episode__season__show=show, episode__season__number=1, episode__number=1, language="de-AT"
    )
    assert first.name == "Geheimnisse"
    assert first.overview
    assert show.seasons.filter(number__gt=0).count() == 3


@pytest.mark.django_db
def test_details_include_streaming_providers(settings):
    settings.DEFAULT_REGION = "DE"

    title = services.get_title("tv", 70523, "de-DE").title

    # "Dark" is a Netflix original; TMDB sends the providers with the details
    offers = title.watch_providers["DE"]
    assert any(p["name"] == "Netflix" for p in offers.get("flatrate", []))
    assert offers["link"].startswith("https://www.themoviedb.org/tv/70523")
