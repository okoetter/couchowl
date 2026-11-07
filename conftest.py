"""Shared pytest fixtures (pytest finds this file automatically)."""

import pytest
from django.core.cache import cache

from accounts.models import User

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
