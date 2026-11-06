from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Invitation, User

PASSWORD = "Long-enough-Pa55word"


@pytest.fixture
def invitation(db):
    return Invitation.objects.create(email="anna@example.com")


def register(client, invitation, **data):
    payload = {"username": "anna", "email": "", "password1": PASSWORD, "password2": PASSWORD}
    payload.update(data)
    return client.post(reverse("accounts:register", args=[invitation.token]), payload)


def test_new_invitation_has_random_token_and_expiry(invitation, settings):
    other = Invitation.objects.create()

    assert len(invitation.token) >= 40
    assert invitation.token != other.token
    expected = timezone.now() + timedelta(days=settings.INVITATION_EXPIRY_DAYS)
    assert abs(invitation.expires_at - expected) < timedelta(minutes=1)
    assert invitation.is_usable


def test_registration_form_is_prefilled_with_invitation_email(client, invitation):
    response = client.get(reverse("accounts:register", args=[invitation.token]))

    assert response.status_code == 200
    assert 'value="anna@example.com"' in response.content.decode()


def test_registration_creates_user_logs_in_and_uses_invitation(client, invitation):
    response = register(client, invitation, email="anna@example.com")

    assert response["Location"] == reverse("core:dashboard")
    user = User.objects.get(username="anna")
    assert user.email == "anna@example.com"
    assert user.check_password(PASSWORD)
    invitation.refresh_from_db()
    assert invitation.used_by == user
    assert invitation.used_at is not None
    assert not invitation.is_usable
    # logged in right away
    assert client.get(reverse("core:dashboard")).status_code == 200


def test_email_is_optional(client, invitation):
    register(client, invitation, email="")

    assert User.objects.get(username="anna").email == ""


def test_invitation_can_only_be_used_once(client, invitation):
    register(client, invitation)
    client.logout()

    response = register(client, invitation, username="mallory")

    assert response.status_code == 410
    assert not User.objects.filter(username="mallory").exists()


def test_expired_invitation_is_rejected(client, invitation):
    invitation.expires_at = timezone.now() - timedelta(minutes=1)
    invitation.save()

    assert client.get(reverse("accounts:register", args=[invitation.token])).status_code == 410
    assert register(client, invitation).status_code == 410
    assert not User.objects.filter(username="anna").exists()


def test_unknown_token_is_rejected(client, db):
    response = client.get(reverse("accounts:register", args=["not-a-real-token"]))

    assert response.status_code == 410
    assert "abgelaufen oder wurde bereits benutzt" in response.content.decode()


def test_password_rules_apply(client, invitation):
    response = register(client, invitation, password1="123", password2="123")

    assert response.status_code == 200
    assert not User.objects.filter(username="anna").exists()
    invitation.refresh_from_db()
    assert invitation.is_usable


def test_email_must_not_belong_to_another_account(client, invitation, user):
    response = register(client, invitation, email="OLIVER@example.com")

    assert response.status_code == 200
    assert "bereits von einem anderen Konto verwendet" in response.content.decode()


def test_logged_in_user_is_sent_to_dashboard(auth_client, invitation):
    response = auth_client.get(reverse("accounts:register", args=[invitation.token]))

    assert response["Location"] == reverse("core:dashboard")
    invitation.refresh_from_db()
    assert invitation.is_usable


def test_usable_queryset(db, user):
    open_ = Invitation.objects.create()
    Invitation.objects.create(expires_at=timezone.now() - timedelta(days=1))
    Invitation.objects.create(used_by=user, used_at=timezone.now())

    assert list(Invitation.objects.usable()) == [open_]
