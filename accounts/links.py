"""Build and send invitation and password reset links."""

from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def invitation_url(request, invitation) -> str:
    """Absolute URL of the registration page for this invitation."""
    return request.build_absolute_uri(invitation.get_absolute_url())


def password_reset_url(request, user) -> str:
    """Absolute one-time URL to set a new password (Django's built-in reset flow)."""
    path = reverse(
        "accounts:password_reset_confirm",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    return request.build_absolute_uri(path)


def send_invitation_email(request, invitation) -> None:
    """Send the invitation link to invitation.email in the server's default language."""
    context = {
        "url": invitation_url(request, invitation),
        "expires_at": invitation.expires_at,
        "inviter": request.user,
    }
    # The invitee has no profile yet; the inviter's language is the best guess
    with translation.override(request.user.effective_ui_language):
        subject = render_to_string("accounts/email/invitation_subject.txt", context).strip()
        body = render_to_string("accounts/email/invitation_body.txt", context)
    send_mail(subject, body, None, [invitation.email])
