"""Search page (full page and htmx fragment) and poster proxy."""

import pytest
from django.urls import reverse

from catalog import posters
from conftest import load_tmdb_fixture, tiny_png

SEARCH = reverse("catalog:search")
HTMX = {"HX-Request": "true"}


@pytest.fixture
def search_response(fake_tmdb):
    fake_tmdb.add("/3/search/multi", json=load_tmdb_fixture("search_multi"))
    return fake_tmdb


# --- Search page --------------------------------------------------------------------------


def test_search_page_without_query(auth_client, fake_tmdb):
    response = auth_client.get(SEARCH)

    content = response.content.decode()
    assert response.status_code == 200
    assert 'name="q"' in content
    assert "Gib einen Titel ein" in content
    assert fake_tmdb.requests == []


def test_results_replace_the_import_hint(auth_client, search_response):
    response = auth_client.get(SEARCH, {"q": "dark"}, headers=HTMX)

    assert reverse("imports:page") not in response.content.decode()


def test_search_uses_the_users_tmdb_language(auth_client, user, search_response):
    user.region = "AT"
    user.save()

    auth_client.get(SEARCH, {"q": "dark"})

    assert search_response.requests[0].url.params["language"] == "de-AT"


def test_full_page_with_results_works_without_javascript(auth_client, search_response):
    response = auth_client.get(SEARCH, {"q": "dark"})

    content = response.content.decode()
    assert "<html" in content
    assert 'value="dark"' in content
    assert "Dark Matter – Der Zeitenläufer" in content
    # Original title is shown when it differs; people are left out
    assert "<br>Dark Matter" in content
    assert "<br>The Dark Knight" not in content
    assert "Dark Person" not in content
    assert "Serie · 2024" in content


def test_htmx_request_gets_only_the_results(auth_client, search_response):
    response = auth_client.get(SEARCH, {"q": "dark"}, headers=HTMX)

    content = response.content.decode()
    assert "<html" not in content
    assert "<form" not in content
    assert 'class="search-results"' in content
    assert "The Dark Knight" in content
    assert "HX-Request" in response["Vary"]


def test_history_restore_gets_the_full_page(auth_client, search_response):
    response = auth_client.get(
        SEARCH, {"q": "dark"}, headers={**HTMX, "HX-History-Restore-Request": "true"}
    )

    assert "<html" in response.content.decode()


def test_posters_are_served_locally_never_by_tmdb(auth_client, search_response):
    content = auth_client.get(SEARCH, {"q": "dark"}, headers=HTMX).content.decode()

    assert '/posters/w92/z1DfRQf2CgnROyhVZ6ch8FbWt71.jpg"' in content
    assert "/posters/w185/z1DfRQf2CgnROyhVZ6ch8FbWt71.jpg 2x" in content
    assert "tmdb.org" not in content


def test_nothing_found(auth_client, fake_tmdb):
    fake_tmdb.add("/3/search/multi", json={"page": 1, "results": []})

    content = auth_client.get(SEARCH, {"q": "xyzzy"}, headers=HTMX).content.decode()

    assert "Nichts gefunden für „xyzzy“." in content


def test_search_without_token_explains_the_problem(auth_client, settings):
    settings.TMDB_API_TOKEN = ""

    content = auth_client.get(SEARCH, {"q": "dark"}, headers=HTMX).content.decode()

    assert "TMDB noch nicht eingerichtet" in content


def test_search_when_tmdb_is_down(auth_client, fake_tmdb):
    fake_tmdb.add("/3/search/multi", json={}, status=503)

    response = auth_client.get(SEARCH, {"q": "dark"}, headers=HTMX)

    assert response.status_code == 200
    assert "TMDB ist gerade nicht erreichbar" in response.content.decode()


def test_search_is_rate_limited_per_user(auth_client, search_response, settings):
    settings.SEARCH_RATE_LIMIT = 2

    for _ in range(2):
        auth_client.get(SEARCH, {"q": "dark"}, headers=HTMX)
    content = auth_client.get(SEARCH, {"q": "dark"}, headers=HTMX).content.decode()

    assert "Zu viele Suchanfragen" in content


def test_search_requires_login(client, db):
    response = client.get(SEARCH, {"q": "dark"})

    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_navigation_links_to_search(auth_client):
    content = auth_client.get(SEARCH).content.decode()

    assert f'href="{SEARCH}" aria-current="page"' in content


# --- Poster proxy -------------------------------------------------------------------------


def poster(size="w92", filename="abc.png"):
    return reverse("catalog:poster", args=[size, filename])


def test_poster_is_downloaded_once_and_then_served_from_disk(auth_client, fake_tmdb, settings):
    fake_tmdb.add_image("w92", "abc.png")

    first = auth_client.get(poster())
    second = auth_client.get(poster())

    assert len(fake_tmdb.requests) == 1
    for response in (first, second):
        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert b"".join(response.streaming_content) == tiny_png()
        assert "immutable" in response["Cache-Control"]
        assert "private" in response["Cache-Control"]
    assert (settings.POSTER_CACHE_DIR / "w92" / "abc.png").read_bytes() == tiny_png()


@pytest.mark.parametrize(
    ("size", "filename"),
    [
        ("w9999", "abc.jpg"),  # size not allowed
        ("original", "abc.jpg"),
        ("w92", "abc.exe"),
        ("w92", "..abc.jpg"),
        ("w92", "a b.jpg"),
    ],
)
def test_invalid_poster_urls_are_refused(auth_client, fake_tmdb, size, filename):
    assert auth_client.get(poster(size, filename)).status_code == 404
    assert fake_tmdb.requests == []


def test_poster_unknown_to_tmdb(auth_client, fake_tmdb):
    fake_tmdb.add("/t/p/w92/gone.jpg", status=404)

    assert auth_client.get(poster(filename="gone.jpg")).status_code == 404


def test_poster_when_tmdb_is_down(auth_client, fake_tmdb, settings):
    fake_tmdb.add("/t/p/w92/abc.jpg", status=503)

    assert auth_client.get(poster(filename="abc.jpg")).status_code == 502
    assert not (settings.POSTER_CACHE_DIR / "w92" / "abc.jpg").exists()


def test_posters_require_login(client, db):
    response = client.get(poster())

    assert response.status_code == 302


@pytest.mark.parametrize(
    ("path", "size", "expected"),
    [
        ("/abc.jpg", "w92", "/posters/w92/abc.jpg"),
        ("/abc.jpg", "w780", "/posters/w780/abc.jpg"),  # enlarged poster on detail pages
        ("", "w92", ""),
        ("/abc.jpg", "original", ""),
        ("/../x.jpg", "w92", ""),
    ],
)
def test_poster_url(path, size, expected):
    assert posters.poster_url(path, size) == expected
