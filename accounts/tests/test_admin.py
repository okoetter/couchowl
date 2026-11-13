import pytest
from django.core import mail
from django.urls import reverse

from accounts.models import Invitation


@pytest.fixture
def add_url():
    return reverse("admin:accounts_invitation_add")


def create_invitation(admin_client, add_url, **data):
    payload = {
        "email": "",
        "note": "",
        "expires_at_0": "2099-01-01",
        "expires_at_1": "12:00:00",
    }
    payload.update(data)
    return admin_client.post(add_url, payload)


def test_create_invitation_shows_link(admin_client, admin_user, add_url, settings):
    settings.EMAIL_ENABLED = False

    response = create_invitation(admin_client, add_url, note="For Anna")

    invitation = Invitation.objects.get()
    assert invitation.created_by == admin_user
    change_url = reverse("admin:accounts_invitation_change", args=[invitation.pk])
    assert response["Location"] == change_url
    content = admin_client.get(change_url).content.decode()
    assert f"http://testserver/accounts/register/{invitation.token}/" in content
    assert mail.outbox == []


def test_invitation_with_email_is_sent_when_email_is_enabled(admin_client, add_url, settings):
    settings.EMAIL_ENABLED = True

    create_invitation(admin_client, add_url, email="anna@example.com")

    invitation = Invitation.objects.get()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["anna@example.com"]
    assert invitation.token in mail.outbox[0].body
    assert "Einladung" in mail.outbox[0].subject


def test_send_action_skips_used_and_emailless_invitations(admin_client, admin_user, settings):
    settings.EMAIL_ENABLED = True
    from django.utils import timezone

    sendable = Invitation.objects.create(email="a@example.com")
    Invitation.objects.create(email="b@example.com", used_by=admin_user, used_at=timezone.now())
    Invitation.objects.create(note="no mail")

    admin_client.post(
        reverse("admin:accounts_invitation_changelist"),
        {
            "action": "send_by_email",
            "_selected_action": list(Invitation.objects.values_list("pk", flat=True)),
        },
    )

    assert [m.to for m in mail.outbox] == [[sendable.email]]


def test_reset_link_action_shows_link(admin_client, user):
    response = admin_client.post(
        reverse("admin:accounts_user_changelist"),
        {"action": "create_password_reset_link", "_selected_action": [user.pk]},
        follow=True,
    )

    content = response.content.decode()
    assert "http://testserver/accounts/password/reset/" in content


def test_invitation_link_uses_site_url(admin_client, add_url, settings):
    # Behind a reverse proxy the request may not carry the public host name
    settings.EMAIL_ENABLED = False
    settings.SITE_URL = "https://couchowl.example.com"

    create_invitation(admin_client, add_url)

    invitation = Invitation.objects.get()
    change_url = reverse("admin:accounts_invitation_change", args=[invitation.pk])
    content = admin_client.get(change_url).content.decode()
    assert f"https://couchowl.example.com/accounts/register/{invitation.token}/" in content
