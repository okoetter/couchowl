from django.db import models
from django.utils.translation import gettext_lazy as _


class MediaType(models.TextChoices):
    # Values are TMDB's own names, so they can be used in API paths (/movie/…, /tv/…)
    MOVIE = "movie", _("Movie")
    TV = "tv", _("TV show")


class Title(models.Model):
    """A movie or show from TMDB: the language-independent data.

    Texts (name, description) and the poster depend on the language and live in
    TitleTranslation, one row per language that someone has looked at.
    """

    media_type = models.CharField(_("type"), max_length=5, choices=MediaType.choices)
    tmdb_id = models.PositiveIntegerField(_("TMDB ID"))
    original_title = models.CharField(_("original title"), max_length=500)
    original_language = models.CharField(_("original language"), max_length=10, blank=True)
    # Movies: release date; shows: date of the first episode
    release_date = models.DateField(_("release date"), null=True, blank=True)
    # TMDB status, e.g. "Released", "Returning Series", "Ended" (not translated by TMDB)
    status = models.CharField(_("status"), max_length=50, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("title")
        verbose_name_plural = _("titles")
        constraints = [
            models.UniqueConstraint(fields=["media_type", "tmdb_id"], name="unique_tmdb_title")
        ]

    def __str__(self):
        return f"{self.original_title} ({self.year or '?'})"

    @property
    def year(self) -> int | None:
        return self.release_date.year if self.release_date else None


class TitleTranslation(models.Model):
    """Name, description and poster of a title in one language (cache of TMDB data).

    Missing texts are already filled from other languages when saving
    (see catalog.services.localize), so templates can show them directly.
    """

    title = models.ForeignKey(
        Title, verbose_name=_("title"), on_delete=models.CASCADE, related_name="translations"
    )
    # TMDB language code as requested, e.g. "de-AT"
    language = models.CharField(_("language"), max_length=10)
    name = models.CharField(_("name"), max_length=500)
    overview = models.TextField(_("description"), blank=True)
    # TMDB picks a poster in this language if there is one
    poster_path = models.CharField(_("poster"), max_length=100, blank=True)
    fetched_at = models.DateTimeField(_("loaded from TMDB at"))

    class Meta:
        verbose_name = _("translation")
        verbose_name_plural = _("translations")
        constraints = [
            models.UniqueConstraint(fields=["title", "language"], name="unique_title_language")
        ]

    def __str__(self):
        return f"{self.name} [{self.language}]"
