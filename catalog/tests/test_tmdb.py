"""The low-level TMDB client: authentication, errors, rate limits, images."""

import httpx
import pytest

from catalog import tmdb
from conftest import load_tmdb_fixture, tiny_png


@pytest.fixture
def no_sleep(monkeypatch):
    """Record waits instead of actually sleeping."""
    waits = []
    monkeypatch.setattr(tmdb.time, "sleep", waits.append)
    return waits


def test_token_is_sent_as_bearer_header_not_in_url(fake_tmdb):
    fake_tmdb.add("/3/search/multi", json=load_tmdb_fixture("search_multi"))

    tmdb.get_client().search("dark", "de-DE")

    request = fake_tmdb.requests[0]
    assert request.headers["Authorization"] == "Bearer test-token"
    assert "test-token" not in str(request.url)
    assert request.url.params["language"] == "de-DE"
    assert request.url.params["include_adult"] == "false"


def test_details_include_all_translations(fake_tmdb):
    fake_tmdb.add("/3/tv/70523", json=load_tmdb_fixture("tv_70523"))

    data = tmdb.get_client().details("tv", 70523, "de-AT")

    assert data["original_name"] == "Dark"
    assert fake_tmdb.requests[0].url.params["append_to_response"] == tmdb.DETAILS_APPENDED


def test_movie_details_include_release_dates(fake_tmdb):
    fake_tmdb.add("/3/movie/155", json=load_tmdb_fixture("movie_155"))

    tmdb.get_client().details("movie", 155, "de-DE")

    appended = fake_tmdb.requests[0].url.params["append_to_response"]
    assert appended == tmdb.MOVIE_DETAILS_APPENDED
    assert "release_dates" in appended.split(",")


def test_missing_token_raises_not_configured(settings):
    settings.TMDB_API_TOKEN = ""

    with pytest.raises(tmdb.TMDBNotConfigured):
        tmdb.get_client()


def test_404_raises_not_found(fake_tmdb):
    fake_tmdb.add("/3/movie/1", json={"status_code": 34}, status=404)

    with pytest.raises(tmdb.TMDBNotFound):
        tmdb.get_client().details("movie", 1, "en-US")


@pytest.mark.parametrize("status", [401, 500, 503])
def test_other_errors_raise_tmdb_error(fake_tmdb, status):
    fake_tmdb.add("/3/movie/1", json={}, status=status)

    with pytest.raises(tmdb.TMDBError):
        tmdb.get_client().details("movie", 1, "en-US")


def test_network_problems_raise_tmdb_error():
    def offline(request):
        raise httpx.ConnectError("no route to host")

    client = tmdb.TMDBClient("t", transport=httpx.MockTransport(offline), requests_per_second=0)

    with pytest.raises(tmdb.TMDBError):
        client.search("dark", "en-US")


def test_rate_limit_is_retried_after_waiting(no_sleep):
    answers = iter(
        [
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"results": []}),
        ]
    )
    client = tmdb.TMDBClient(
        "t", transport=httpx.MockTransport(lambda r: next(answers)), requests_per_second=0
    )

    assert client.search("dark", "en-US") == {"results": []}
    assert no_sleep == [2.0]


def test_rate_limit_gives_up_after_retries(no_sleep):
    calls = []

    def always_429(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "999"})

    client = tmdb.TMDBClient("t", transport=httpx.MockTransport(always_429), requests_per_second=0)

    with pytest.raises(tmdb.TMDBError):
        client.search("dark", "en-US")
    assert len(calls) == tmdb.MAX_RETRIES + 1
    # Never waits longer than the cap, even if TMDB asks for more
    assert set(no_sleep) == {tmdb.MAX_RETRY_WAIT_SECONDS}


def test_throttle_spaces_out_requests(no_sleep, monkeypatch):
    monkeypatch.setattr(tmdb.time, "monotonic", lambda: 100.0)
    client = tmdb.TMDBClient(
        "t",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        requests_per_second=10,
    )

    client.get("/a")
    client.get("/b")  # same instant: has to wait 1/10 s

    assert no_sleep == [pytest.approx(0.1)]


def test_image_download_without_token(fake_tmdb):
    fake_tmdb.add_image("w92", "abc.png")

    content, content_type = tmdb.get_client().image("w92", "abc.png")

    assert content == tiny_png()
    assert content_type == "image/png"
    request = fake_tmdb.requests[0]
    assert request.url.host == "image.tmdb.org"
    assert "Authorization" not in request.headers


def test_image_with_wrong_content_type_is_rejected(fake_tmdb):
    fake_tmdb.add("/t/p/w92/abc.jpg", content=b"<html>", headers={"Content-Type": "text/html"})

    with pytest.raises(tmdb.TMDBError):
        tmdb.get_client().image("w92", "abc.jpg")
