"""TMDB ratings: stored with the title, shown on detail pages, in lists and in search."""

import pytest
from django.template import Context, Template
from django.urls import reverse
from django.utils import translation

from catalog import lists, services
from catalog.models import Title
from conftest import load_tmdb_fixture


def render_rating(item, votes=False, language="de-de"):
    template = Template("{% load catalog %}{% rating item votes=votes %}")
    with translation.override(language):
        return template.render(Context({"item": item, "votes": votes}))


# --- Storing -----------------------------------------------------------------------------------


def test_rating_is_stored_with_the_title(movie):
    assert (movie.vote_average, movie.vote_count) == (8.523, 34121)


def test_missing_rating(db):
    data = load_tmdb_fixture("movie_155")
    del data["vote_average"], data["vote_count"]

    title = services.save_title("movie", data, "de-DE").title

    assert (title.vote_average, title.vote_count) == (None, 0)


def test_search_results_carry_the_rating(fake_tmdb, settings):
    fake_tmdb.add("/3/search/multi", json=load_tmdb_fixture("search_multi"))

    results = {r.tmdb_id: r for r in services.search("dark", "de-DE")}

    assert (results[155].vote_average, results[155].vote_count) == (8.523, 34121)


def test_cached_search_results_without_rating_still_load():
    """Search results cached before ratings existed have no such fields."""
    result = services.SearchResult(
        media_type="tv", tmdb_id=1, title="X", original_title="X", year=None, poster_path=""
    )

    assert (result.vote_average, result.vote_count) == (None, 0)


# --- Formatting --------------------------------------------------------------------------------


@pytest.mark.parametrize(("language", "expected"), [("de-de", "★ 8,5"), ("en-us", "★ 8.5")])
def test_rating_is_formatted_for_the_region(language, expected):
    assert expected in render_rating(Title(vote_average=8.523, vote_count=50), language=language)


def test_overviews_hide_ratings_with_few_votes():
    assert render_rating(Title(vote_average=10.0, vote_count=9)) == ""
    assert "★ 7,0" in render_rating(Title(vote_average=7.0, vote_count=10))
    assert render_rating(Title(vote_average=None, vote_count=0)) == ""


def test_detail_page_shows_the_votes_from_one_vote():
    assert "★ 10,0 (2 Stimmen)" in render_rating(Title(vote_average=10.0, vote_count=2), True)
    assert "★ 6,0 (1 Stimme)" in render_rating(Title(vote_average=6.0, vote_count=1), True)
    assert "★ 8,5 (34.121 Stimmen)" in render_rating(
        Title(vote_average=8.523, vote_count=34121), True
    )
    assert render_rating(Title(vote_average=0.0, vote_count=0), True) == ""


def test_screen_readers_get_a_full_sentence():
    html = render_rating(Title(vote_average=8.523, vote_count=34121))

    assert '<span aria-hidden="true">★ 8,5</span>' in html
    assert "TMDB-Bewertung: 8,5 von 10 (34.121 Stimmen)" in html


# --- Pages -------------------------------------------------------------------------------------


def test_detail_page(auth_client, movie):
    content = auth_client.get(movie.get_absolute_url()).content.decode()

    assert "★ 8,5 (34.121 Stimmen)" in content


def test_search_page(auth_client, fake_tmdb):
    fake_tmdb.add("/3/search/multi", json=load_tmdb_fixture("search_multi"))

    content = auth_client.get(reverse("catalog:search"), {"q": "dark"}).content.decode()

    assert "★ 8,5" in content  # The Dark Knight
    assert "★ 8,4" in content  # Dark
    assert "★ 6,1" not in content  # only 4 votes


@pytest.mark.parametrize("layout", ["grid", "compact"])
def test_list_page(auth_client, user, movie, layout):
    user.list_layout = layout
    user.save()
    watchlist = user.lists.create(name="Watchlist")
    lists.add_to_list(watchlist, movie)

    content = auth_client.get(watchlist.get_absolute_url()).content.decode()

    assert "★ 8,5" in content
