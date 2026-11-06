from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .links import invitation_url, password_reset_url, send_invitation_email
from .models import Invitation, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        (_("Preferences"), {"fields": ("ui_language", "tmdb_language", "region", "theme")}),
    )
    actions = ["create_password_reset_link"]

    @admin.action(description=_("Create password reset link"))
    def create_password_reset_link(self, request, queryset):
        """Shows a one-time link per user, e.g. to send it via messenger (works without SMTP)."""
        for user in queryset:
            self.message_user(
                request,
                format_html(
                    "{}: <code>{}</code>",
                    _("Password reset link for %(user)s") % {"user": user},
                    password_reset_url(request, user),
                ),
                messages.SUCCESS,
            )


class InvitationStatusFilter(admin.SimpleListFilter):
    title = _("status")
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return [("open", _("Open")), ("used", _("Used")), ("expired", _("Expired"))]

    def queryset(self, request, queryset):
        match self.value():
            case "open":
                return queryset.usable()
            case "used":
                return queryset.filter(used_at__isnull=False)
            case "expired":
                return queryset.filter(used_at__isnull=True, expires_at__lte=timezone.now())
        return queryset


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["__str__", "status", "expires_at", "created_by", "used_by"]
    list_filter = [InvitationStatusFilter]
    search_fields = ["email", "note", "used_by__username"]
    fields = ["email", "note", "expires_at", "created_by", "created_at", "used_by", "used_at"]
    readonly_fields = ["created_by", "created_at", "used_by", "used_at"]
    actions = ["send_by_email"]

    @admin.display(description=_("status"))
    def status(self, invitation):
        if invitation.is_used:
            return _("Used")
        if invitation.is_expired:
            return _("Expired")
        return _("Open")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        if not change and obj.email and settings.EMAIL_ENABLED:
            self._send(request, obj)

    def render_change_form(self, request, context, *args, obj=None, **kwargs):
        # Shown above the form (see templates/admin/accounts/invitation/change_form.html)
        if obj is not None and obj.is_usable:
            context["invitation_url"] = invitation_url(request, obj)
        return super().render_change_form(request, context, *args, obj=obj, **kwargs)

    def response_add(self, request, obj, post_url_continue=None):
        # After "Save", open the new invitation so the admin can copy its link right away
        if "_addanother" in request.POST or IS_POPUP_VAR in request.POST:
            return super().response_add(request, obj, post_url_continue)
        self.message_user(request, _("Invitation created. Copy the link below."), messages.SUCCESS)
        return redirect("admin:accounts_invitation_change", obj.pk)

    @admin.action(description=_("Send invitation by e-mail"))
    def send_by_email(self, request, queryset):
        if not settings.EMAIL_ENABLED:
            self.message_user(
                request, _("Sending e-mail is not configured (EMAIL_URL)."), messages.ERROR
            )
            return
        for invitation in queryset:
            if not invitation.is_usable:
                self.message_user(
                    request,
                    _("%(invitation)s is used or expired and was skipped.")
                    % {"invitation": invitation},
                    messages.WARNING,
                )
            elif not invitation.email:
                self.message_user(
                    request,
                    _("%(invitation)s has no e-mail address and was skipped.")
                    % {"invitation": invitation},
                    messages.WARNING,
                )
            else:
                self._send(request, invitation)

    def _send(self, request, invitation):
        try:
            send_invitation_email(request, invitation)
        except Exception as error:  # e.g. SMTP server unreachable
            self.message_user(
                request,
                _("Could not send e-mail to %(email)s: %(error)s")
                % {"email": invitation.email, "error": error},
                messages.ERROR,
            )
        else:
            self.message_user(
                request,
                _("Invitation sent to %(email)s.") % {"email": invitation.email},
                messages.SUCCESS,
            )
