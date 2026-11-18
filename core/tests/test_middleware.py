"""Data version cookie: lets pages restored by the back button notice changes."""

import re

from django.urls import reverse

from core.middleware import DataVersionMiddleware

COOKIE = DataVersionMiddleware.COOKIE


def page_version(response) -> str:
    return re.search(r'<main [^>]*data-version="([^"]*)"', response.content.decode()).group(1)


def test_pages_carry_the_version_from_the_cookie(client, user):
    client.force_login(user)
    client.cookies[COOKIE] = "123"

    response = client.get(reverse("core:dashboard"))

    assert page_version(response) == "123"
    assert COOKIE not in response.cookies  # reading changes nothing


def test_a_change_sets_a_new_version(client, user):
    client.force_login(user)
    client.cookies[COOKIE] = "123"

    # Invalid form: the page is rendered by the POST itself
    response = client.post(reverse("accounts:profile"), {})

    assert response.status_code == 200
    cookie = response.cookies[COOKIE]
    assert cookie.value not in ("", "123")
    assert not cookie["httponly"]  # couchowl.js reads it
    assert cookie["samesite"] == "Lax"
    # The page made by the change already shows the new state
    assert page_version(response) == cookie.value


def test_failed_changes_keep_the_version(client, user):
    client.force_login(user)

    response = client.post(reverse("catalog:list_delete", args=[999]))

    assert response.status_code == 404
    assert COOKIE not in response.cookies
