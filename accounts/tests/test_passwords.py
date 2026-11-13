import re

import pytest
from django.core import mail
from django.urls import reverse

from accounts.models import User
from conftest import PASSWORD

NEW_PASSWORD = "Another-long-Pa55word"


def test_change_password(auth_client, user):
    response = auth_client.post(
        reverse("accounts:password_change"),
        {"old_password": PASSWORD, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
    )

    assert response["Location"] == reverse("accounts:profile")
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    # still logged in
    assert auth_client.get(reverse("accounts:profile")).status_code == 200


def test_change_password_requires_old_password(auth_client, user):
    auth_client.post(
        reverse("accounts:password_change"),
        {"old_password": "wrong", "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
    )

    user.refresh_from_db()
    assert user.check_password(PASSWORD)


# --- "Forgot password" ----------------------------------------------------------


def test_login_page_links_to_reset_when_email_is_enabled(client, db, settings):
    settings.EMAIL_ENABLED = True

    content = client.get(reverse("accounts:login")).content.decode()

    assert reverse("accounts:password_reset") in content


def test_without_email_reset_is_hidden_and_disabled(client, db, settings):
    settings.EMAIL_ENABLED = False

    content = client.get(reverse("accounts:login")).content.decode()

    assert reverse("accounts:password_reset") not in content
    assert "Administrator" in content
    assert client.get(reverse("accounts:password_reset")).status_code == 404
    assert client.post(reverse("accounts:password_reset"), {"email": "x@y.z"}).status_code == 404


def request_reset(client, email):
    return client.post(reverse("accounts:password_reset"), {"email": email})


def test_reset_email_contains_working_link(client, user):
    response = request_reset(client, "oliver@example.com")

    assert response["Location"] == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["oliver@example.com"]
    assert message.subject == "Dein Couch-Owl-Passwort zurücksetzen"
    path = re.search(r"https?://[^/]+(/\S+)", message.body).group(1)

    # Django redirects the token URL to a session-based URL before showing the form
    form_page = client.get(path, follow=True)
    assert form_page.status_code == 200
    client.post(
        form_page.redirect_chain[-1][0],
        {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
    )
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


def test_reset_does_not_reveal_unknown_email(client, user):
    response = request_reset(client, "nobody@example.com")

    assert response["Location"] == reverse("accounts:password_reset_done")
    assert mail.outbox == []


def test_reset_requests_are_rate_limited(client, user, settings):
    for _ in range(settings.PASSWORD_RESET_RATE_LIMIT):
        assert request_reset(client, "oliver@example.com").status_code == 302

    response = request_reset(client, "oliver@example.com")

    assert response.status_code == 429
    assert len(mail.outbox) == settings.PASSWORD_RESET_RATE_LIMIT


def test_reset_link_works_without_email(client, user, settings):
    """Admins create reset links in the admin when SMTP is not configured."""
    settings.EMAIL_ENABLED = False
    from django.test import RequestFactory

    from accounts.links import password_reset_url

    url = password_reset_url(RequestFactory().get("/"), user)

    assert client.get(url, follow=True).status_code == 200


def test_invalid_reset_link_shows_message(client, db):
    response = client.get(
        reverse("accounts:password_reset_confirm", args=["MQ", "invalid-token"]), follow=True
    )

    assert "ungültig oder abgelaufen" in response.content.decode()


# --- Brute-force protection (django-axes) ----------------------------------------


@pytest.mark.django_db
def test_login_is_locked_after_too_many_failures(client, user, settings):
    login_url = reverse("accounts:login")
    for _ in range(settings.AXES_FAILURE_LIMIT):
        client.post(login_url, {"username": "oliver", "password": "wrong"})

    # even the correct password is refused now
    response = client.post(login_url, {"username": "oliver", "password": PASSWORD})

    assert response.status_code == 429
    assert "Anmeldung gesperrt" in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_other_users_are_not_affected_by_a_lockout(client, user, settings):
    User.objects.create_user(username="anna", password=PASSWORD)
    login_url = reverse("accounts:login")
    for _ in range(settings.AXES_FAILURE_LIMIT):
        client.post(login_url, {"username": "oliver", "password": "wrong"})

    response = client.post(login_url, {"username": "anna", "password": PASSWORD})

    assert response.status_code == 302


# --- Behind a reverse proxy --------------------------------------------------------
# All requests come from the proxy's address; the client is in X-Forwarded-For.

PROXY = {"REMOTE_ADDR": "172.18.0.1"}


def from_client(address):
    return {**PROXY, "HTTP_X_FORWARDED_FOR": address}


def test_lockout_is_per_client_behind_a_proxy(client, user, settings):
    settings.TRUSTED_PROXY_COUNT = 1
    login_url = reverse("accounts:login")
    for _ in range(settings.AXES_FAILURE_LIMIT):
        client.post(
            login_url, {"username": "oliver", "password": "wrong"}, **from_client("203.0.113.5")
        )

    attacker = client.post(
        login_url, {"username": "oliver", "password": PASSWORD}, **from_client("203.0.113.5")
    )
    owner = client.post(
        login_url, {"username": "oliver", "password": PASSWORD}, **from_client("2001:db8::7")
    )

    assert attacker.status_code == 429
    assert owner.status_code == 302


def test_forged_forwarded_for_does_not_escape_the_lockout(client, user, settings):
    settings.TRUSTED_PROXY_COUNT = 1
    login_url = reverse("accounts:login")
    for attempt in range(settings.AXES_FAILURE_LIMIT):
        # The attacker sends a new fake address each time; the proxy appends the real one
        client.post(
            login_url,
            {"username": "oliver", "password": "wrong"},
            **from_client(f"10.9.9.{attempt}, 203.0.113.5"),
        )

    response = client.post(
        login_url, {"username": "oliver", "password": PASSWORD}, **from_client("203.0.113.5")
    )

    assert response.status_code == 429


def test_reset_rate_limit_is_per_client_behind_a_proxy(client, user, settings):
    settings.TRUSTED_PROXY_COUNT = 1
    url = reverse("accounts:password_reset")
    for _ in range(settings.PASSWORD_RESET_RATE_LIMIT + 1):
        client.post(url, {"email": "oliver@example.com"}, **from_client("203.0.113.5"))

    other = client.post(url, {"email": "oliver@example.com"}, **from_client("198.51.100.8"))

    assert other.status_code == 302


def test_reset_email_link_uses_site_url(client, user, settings):
    settings.SITE_URL = "https://couchowl.example.com"

    request_reset(client, "oliver@example.com")

    assert "https://couchowl.example.com/accounts/password/reset/" in mail.outbox[0].body
