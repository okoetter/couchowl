"""Fixtures for the catalog tests: stored titles and a second user."""

import pytest

from accounts.models import User
from catalog import services
from conftest import PASSWORD, load_tmdb_fixture


@pytest.fixture
def movie(db):
    """ "The Dark Knight", stored in German (the test user's TMDB language)."""
    return services.save_title("movie", load_tmdb_fixture("movie_155"), "de-DE").title


@pytest.fixture
def show(db):
    """ "Dark", stored in German."""
    return services.save_title("tv", load_tmdb_fixture("tv_70523"), "de-DE").title


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="eve", password=PASSWORD, region="DE")
