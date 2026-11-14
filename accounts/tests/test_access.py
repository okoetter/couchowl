"""Every page requires login, except a few public ones."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "core:dashboard",
        "catalog:lists",
        "core:upcoming",
        "catalog:search",
        "accounts:profile",
        "accounts:password_change",
    ],
)
def test_pages_redirect_anonymous_users_to_login(client, url_name):
    url = reverse(url_name)

    response = client.get(url)

    assert response.status_code == 302
    assert response["Location"] == f"{reverse('accounts:login')}?next={url}"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name", ["accounts:login", "accounts:password_reset", "core:health", "core:manifest"]
)
def test_public_pages_are_reachable_without_login(client, url_name):
    assert client.get(reverse(url_name)).status_code == 200


def test_navigation_is_hidden_when_logged_out(client, db):
    content = client.get(reverse("accounts:login")).content.decode()

    assert reverse("catalog:lists") not in content


def test_login_redirects_to_next_page(client, user):
    from conftest import PASSWORD

    response = client.post(
        reverse("accounts:login"),
        {"username": "anna", "password": PASSWORD, "next": reverse("catalog:lists")},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("catalog:lists")


def test_logout_requires_post_and_logs_out(auth_client):
    response = auth_client.post(reverse("accounts:logout"))

    assert response["Location"] == reverse("accounts:login")
    assert auth_client.get(reverse("core:dashboard")).status_code == 302


def test_wrong_password_shows_form_error(client, user):
    response = client.post(reverse("accounts:login"), {"username": "anna", "password": "wrong"})

    content = response.content.decode()
    assert response.status_code == 200
    # styled red via .errorlist.nonfield in couchowl.css
    assert '<ul class="errorlist nonfield">' in content
    assert "Benutzername oder Passwort ist falsch." in content
