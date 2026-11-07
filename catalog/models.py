from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
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

    def get_absolute_url(self):
        return reverse("catalog:title_detail", args=[self.media_type, self.tmdb_id])

    @property
    def year(self) -> int | None:
        return self.release_date.year if self.release_date else None

    @property
    def is_movie(self) -> bool:
        return self.media_type == MediaType.MOVIE

    @property
    def status_label(self) -> str:
        return status_label(self.status)


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


# TMDB status values are English; these are the ones TMDB documents
_STATUS_LABELS = {
    "Released": _("Released"),
    "Rumored": _("Rumored"),
    "Planned": _("Planned"),
    "In Production": _("In production"),
    "Post Production": _("Post-production"),
    "Canceled": _("Canceled"),
    "Returning Series": _("Returning series"),
    "Ended": _("Ended"),
    "Pilot": _("Pilot"),
}


def status_label(status: str) -> str:
    """Translated TMDB status; unknown values are shown as TMDB sends them."""
    return _STATUS_LABELS.get(status, status)


class UserList(models.Model):
    """A private list of movies and shows, e.g. "Watchlist" or "Watch with family"."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="lists",
    )
    name = models.CharField(_("name"), max_length=100)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("list")
        verbose_name_plural = _("lists")
        ordering = [Lower("name")]
        constraints = [
            # "Watchlist" and "watchlist" would be confusing next to each other
            models.UniqueConstraint("user", Lower("name"), name="unique_list_name_per_user"),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("catalog:list_detail", args=[self.pk])


class ListItem(models.Model):
    user_list = models.ForeignKey(
        UserList, verbose_name=_("list"), on_delete=models.CASCADE, related_name="items"
    )
    title = models.ForeignKey(
        Title, verbose_name=_("title"), on_delete=models.CASCADE, related_name="list_items"
    )
    added_at = models.DateTimeField(_("added at"), auto_now_add=True)

    class Meta:
        verbose_name = _("list entry")
        verbose_name_plural = _("list entries")
        ordering = ["-added_at", "-pk"]  # newest first
        constraints = [
            models.UniqueConstraint(fields=["user_list", "title"], name="unique_title_per_list")
        ]

    def __str__(self):
        return f"{self.title} @ {self.user_list}"


class WatchedMovie(models.Model):
    """A movie the user has seen. Only the last date is kept (no history)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="watched_movies",
    )
    title = models.ForeignKey(
        Title,
        verbose_name=_("movie"),
        on_delete=models.CASCADE,
        related_name="watched_by",
        limit_choices_to={"media_type": MediaType.MOVIE},
    )
    # Empty = seen, but the date is unknown
    watched_at = models.DateField(_("watched on"), null=True, blank=True)

    class Meta:
        verbose_name = _("watched movie")
        verbose_name_plural = _("watched movies")
        constraints = [
            models.UniqueConstraint(fields=["user", "title"], name="unique_watched_movie")
        ]

    def __str__(self):
        return f"{self.user} ✓ {self.title}"
