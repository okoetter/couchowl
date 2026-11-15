"""Fixtures for the import tests: a fake TMDB search answering per query."""

import pytest

from conftest import load_tmdb_fixture


def movie(tmdb_id, title, year, original=None):
    """A movie as TMDB's /search/multi returns it."""
    return {
        "media_type": "movie",
        "id": tmdb_id,
        "title": title,
        "original_title": original or title,
        "release_date": f"{year}-06-01" if year else "",
        "poster_path": f"/m{tmdb_id}.jpg",
    }


def tv(tmdb_id, name, year, original=None):
    return {
        "media_type": "tv",
        "id": tmdb_id,
        "name": name,
        "original_name": original or name,
        "first_air_date": f"{year}-12-01" if year else "",
        "poster_path": f"/t{tmdb_id}.jpg",
    }


@pytest.fixture
def searches(fake_tmdb):
    """{query (lower case): [results]}; queries not in it find nothing.

    Also registers "The Dark Knight" (movie 155) and "Dark" (show 70523) for loading.
    """
    results = {}

    def respond(request):
        return {"results": results.get(request.url.params["query"].casefold(), [])}

    fake_tmdb.add("/3/search/multi", json=respond)
    fake_tmdb.add("/3/movie/155", json=load_tmdb_fixture("movie_155"))
    fake_tmdb.add_show()
    results["dark"] = [
        movie(155, "The Dark Knight", 2008),
        tv(70523, "Dark", 2017),
        movie(500, "Dark", 2005),
    ]
    results["the dark knight"] = [movie(155, "The Dark Knight", 2008)]
    return results
