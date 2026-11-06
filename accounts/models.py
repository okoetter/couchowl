from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """watchit user. A custom model from day one makes later changes painless."""

    class Theme(models.TextChoices):
        AUTO = "auto", _("Automatic (system)")
        LIGHT = "light", _("Light")
        DARK = "dark", _("Dark")

    # Empty value = use the server default from the environment (.env)
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
    region = models.CharField(
        _("region"),
        max_length=2,
        blank=True,
        help_text=_(
            "Country for streaming providers and release dates, e.g. DE. "
            "Empty: derived from the language for movie and show information."
        ),
    )
    theme = models.CharField(
        _("color scheme"), max_length=10, choices=Theme.choices, default=Theme.AUTO
    )

    @property
    def effective_ui_language(self) -> str:
        return self.ui_language or settings.LANGUAGE_CODE

    @property
    def effective_tmdb_language(self) -> str:
        return self.tmdb_language or settings.DEFAULT_TMDB_LANGUAGE

    @property
    def effective_region(self) -> str:
        """Explicit region > server default > country part of the TMDB language."""
        if self.region:
            return self.region.upper()
        if settings.DEFAULT_REGION:
            return settings.DEFAULT_REGION.upper()
        return region_from_language(self.effective_tmdb_language)


def region_from_language(language: str, fallback: str = "US") -> str:
    """'de-DE' -> 'DE', 'en' -> fallback."""
    parts = language.replace("_", "-").split("-")
    if len(parts) >= 2 and len(parts[1]) == 2:
        return parts[1].upper()
    return fallback
