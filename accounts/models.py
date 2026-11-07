import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .regions import default_region, tmdb_language_for_region, ui_language_for_region


class User(AbstractUser):
    """watchit user. A custom model from day one makes later changes painless."""

    class Theme(models.TextChoices):
        AUTO = "auto", _("Automatic (system)")
        LIGHT = "light", _("Light")
        DARK = "dark", _("Dark")

    # Region is the main setting; both languages are derived from it unless set.
    # Empty region: detected from the browser on the next request (see middleware).
    region = models.CharField(
        _("region"),
        max_length=2,
        blank=True,
        help_text=_(
            "Country for streaming providers and release dates, e.g. DE. "
            "Also determines the languages unless you choose them yourself."
        ),
    )
    # Empty value = automatic (derived from the region)
    ui_language = models.CharField(
        _("interface language"),
        max_length=10,
        blank=True,
        choices=settings.LANGUAGES,
    )
    tmdb_language = models.CharField(
        _("language for movie and show information"),
        max_length=10,
        blank=True,
        help_text=_("TMDB language code, e.g. de-DE or en-US."),
    )
    theme = models.CharField(
        _("color scheme"), max_length=10, choices=Theme.choices, default=Theme.AUTO
    )

    class ListLayout(models.TextChoices):
        GRID = "grid", _("Poster grid")
        COMPACT = "compact", _("Compact list")

    # Switched on the list page itself, applies to all lists
    list_layout = models.CharField(
        _("list layout"), max_length=10, choices=ListLayout.choices, default=ListLayout.GRID
    )
    show_followed_list = models.BooleanField(
        _("show “Followed shows” list"),
        default=True,
        help_text=_("A list of all shows you follow, shown on the “Lists” page."),
    )

    @property
    def effective_region(self) -> str:
        """Saved region > server default (DEFAULT_REGION) > US."""
        return self.region.upper() if self.region else default_region()

    @property
    def effective_ui_language(self) -> str:
        """Chosen language > main language of the region (if translated) > English."""
        return self.ui_language or ui_language_for_region(self.effective_region)

    @property
    def effective_tmdb_language(self) -> str:
        """Chosen language > main language of the region plus country, e.g. de-AT."""
        return self.tmdb_language or tmdb_language_for_region(self.effective_region)


def _new_invitation_token() -> str:
    return secrets.token_urlsafe(32)


def _default_invitation_expiry():
    return timezone.now() + timedelta(days=settings.INVITATION_EXPIRY_DAYS)


class InvitationQuerySet(models.QuerySet):
    def usable(self):
        """Invitations that can still be used to register."""
        return self.filter(used_by__isnull=True, expires_at__gt=timezone.now())


class Invitation(models.Model):
    """A one-time link that allows exactly one person to create an account."""

    token = models.CharField(
        _("token"), max_length=64, unique=True, default=_new_invitation_token, editable=False
    )
    email = models.EmailField(
        _("e-mail"),
        blank=True,
        help_text=_("Optional. Pre-fills the registration form and is used to send the link."),
    )
    note = models.CharField(
        _("note"), max_length=200, blank=True, help_text=_("Only visible to admins.")
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    expires_at = models.DateTimeField(_("expires at"), default=_default_invitation_expiry)
    used_by = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("used by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitation",
        editable=False,
    )
    used_at = models.DateTimeField(_("used at"), null=True, blank=True, editable=False)

    objects = InvitationQuerySet.as_manager()

    class Meta:
        verbose_name = _("invitation")
        verbose_name_plural = _("invitations")
        ordering = ["-created_at"]

    def __str__(self):
        return self.email or self.note or _("Invitation #%(id)s") % {"id": self.pk}

    def get_absolute_url(self):
        return reverse("accounts:register", args=[self.token])

    @property
    def is_used(self) -> bool:
        return self.used_by_id is not None or self.used_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_usable(self) -> bool:
        return not self.is_used and not self.is_expired
