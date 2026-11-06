from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone, translation
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.debug import sensitive_post_parameters

from . import throttle
from .forms import ProfileForm, RegistrationForm
from .models import Invitation


@login_not_required
@sensitive_post_parameters("password1", "password2")
def register(request, token):
    """Create an account with a valid invitation link and log in right away."""
    invitation = Invitation.objects.filter(token=token).first()
    if invitation is None or not invitation.is_usable:
        return render(request, "accounts/invitation_invalid.html", status=410)
    if request.user.is_authenticated:
        messages.info(request, _("You are already logged in."))
        return redirect("core:dashboard")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Mark the invitation as used only if nobody else did it in the meantime
                claimed = (
                    Invitation.objects.usable()
                    .filter(pk=invitation.pk)
                    .update(used_at=timezone.now())
                )
                if not claimed:
                    return render(request, "accounts/invitation_invalid.html", status=410)
                user = form.save()
                Invitation.objects.filter(pk=invitation.pk).update(used_by=user)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, _("Welcome to watchit, %(name)s!") % {"name": user})
            return redirect("core:dashboard")
    else:
        form = RegistrationForm(initial={"email": invitation.email})

    return render(request, "accounts/register.html", {"form": form, "invitation": invitation})


def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            # Show the confirmation already in the newly chosen language
            translation.activate(request.user.effective_ui_language)
            messages.success(request, _("Your profile has been saved."))
            # Redirect so the new language/theme applies and reloading doesn't resubmit
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})


class PasswordChangeView(SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")
    success_message = gettext_lazy("Your password has been changed.")


class EmailRequiredMixin:
    """'Forgot password' by e-mail only exists when sending e-mail is configured."""

    # Overriding dispatch() hides Django's own @login_not_required marker, so repeat it
    @method_decorator(login_not_required)
    def dispatch(self, request, *args, **kwargs):
        if not settings.EMAIL_ENABLED:
            raise Http404
        return super().dispatch(request, *args, **kwargs)


class PasswordResetView(EmailRequiredMixin, auth_views.PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    subject_template_name = "accounts/email/password_reset_subject.txt"
    email_template_name = "accounts/email/password_reset_body.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def post(self, request, *args, **kwargs):
        allowed = throttle.hit(
            f"password_reset:{throttle.client_ip(request)}",
            limit=settings.PASSWORD_RESET_RATE_LIMIT,
            window_seconds=3600,
        )
        if not allowed:
            return render(request, "accounts/rate_limited.html", status=429)
        return super().post(request, *args, **kwargs)


class PasswordResetDoneView(EmailRequiredMixin, auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


# Confirm/complete also work without e-mail: admins can create reset links in the admin.
class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
