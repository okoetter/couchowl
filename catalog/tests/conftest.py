"""Fixtures for the catalog tests: stored titles and a second user."""

import pytest

from accounts.models import User
from catalog import services
from conftest import PASSWORD, dark_seasons, load_tmdb_fixture


@pytest.fixture
def movie(db):
    """ "The Dark Knight", stored in German (the test user's TMDB language)."""
    return services.save_title("movie", load_tmdb_fixture("movie_155"), "de-DE").title


@pytest.fixture
def show(db):
    """ "Dark" with its seasons and episodes, stored in German."""
    data = load_tmdb_fixture("tv_70523")
    return services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="eve", password=PASSWORD, region="DE")
