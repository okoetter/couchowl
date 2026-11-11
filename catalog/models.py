from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
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
    # Shows: names of the networks/platforms that air it, e.g. ["Netflix"] (from TMDB)
    networks = models.JSONField(_("networks"), default=list, blank=True)
    # Streaming providers per region (data from JustWatch via TMDB), only for the regions
    # of our users: {"DE": {"link": "…", "flatrate": [{"id": 8, "name": "Netflix",
    # "logo": "/….png"}], "rent": […], …}}. {} for a region = no offers there.
    # See catalog.providers.
    watch_providers = models.JSONField(_("streaming providers"), default=dict, blank=True)
    # TMDB user rating: average of 0-10 and number of votes (see catalog.templatetags)
    vote_average = models.FloatField(_("TMDB rating"), null=True, blank=True)
    vote_count = models.PositiveIntegerField(_("TMDB votes"), default=0)
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

    # The computed list "Followed shows" (catalog.lists.FollowedShows) is a system list
    is_system = False

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


# --- Seasons and episodes --------------------------------------------------------------------


class Season(models.Model):
    """A season of a show. Number 0 holds TMDB's specials ("Season 0")."""

    show = models.ForeignKey(
        Title,
        verbose_name=_("TV show"),
        on_delete=models.CASCADE,
        related_name="seasons",
        limit_choices_to={"media_type": MediaType.TV},
    )
    number = models.PositiveSmallIntegerField(_("number"))
    air_date = models.DateField(_("air date"), null=True, blank=True)

    class Meta:
        verbose_name = _("season")
        verbose_name_plural = _("seasons")
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["show", "number"], name="unique_season_number")
        ]

    def __str__(self):
        return f"{self.show.original_title} S{self.number}"

    @property
    def is_specials(self) -> bool:
        return self.number == 0


class SeasonTranslation(models.Model):
    """Name and description of a season in one language (same idea as TitleTranslation)."""

    season = models.ForeignKey(
        Season, verbose_name=_("season"), on_delete=models.CASCADE, related_name="translations"
    )
    language = models.CharField(_("language"), max_length=10)
    name = models.CharField(_("name"), max_length=500, blank=True)
    overview = models.TextField(_("description"), blank=True)

    class Meta:
        verbose_name = _("season translation")
        verbose_name_plural = _("season translations")
        constraints = [
            models.UniqueConstraint(fields=["season", "language"], name="unique_season_language")
        ]

    def __str__(self):
        return f"{self.name} [{self.language}]"


class Episode(models.Model):
    season = models.ForeignKey(
        Season, verbose_name=_("season"), on_delete=models.CASCADE, related_name="episodes"
    )
    number = models.PositiveSmallIntegerField(_("number"))
    # Kept for later imports (e.g. JustWatch); episodes are addressed by their numbers
    tmdb_id = models.PositiveIntegerField(_("TMDB ID"), null=True, blank=True)
    # Empty or in the future: not aired yet, can't be marked as watched
    air_date = models.DateField(_("air date"), null=True, blank=True)
    runtime = models.PositiveSmallIntegerField(_("runtime (minutes)"), null=True, blank=True)

    class Meta:
        verbose_name = _("episode")
        verbose_name_plural = _("episodes")
        ordering = ["season__number", "number"]
        constraints = [
            models.UniqueConstraint(fields=["season", "number"], name="unique_episode_number")
        ]

    def __str__(self):
        return f"{self.season} E{self.number}"

    @property
    def code(self) -> str:
        """Short name like "S2 E5"."""
        return gettext("S%(season)s E%(episode)s") % {
            "season": self.season.number,
            "episode": self.number,
        }

    def has_aired(self, today=None) -> bool:
        return self.air_date is not None and self.air_date <= (today or timezone.localdate())


class EpisodeTranslation(models.Model):
    episode = models.ForeignKey(
        Episode, verbose_name=_("episode"), on_delete=models.CASCADE, related_name="translations"
    )
    language = models.CharField(_("language"), max_length=10)
    name = models.CharField(_("name"), max_length=500, blank=True)
    overview = models.TextField(_("description"), blank=True)

    class Meta:
        verbose_name = _("episode translation")
        verbose_name_plural = _("episode translations")
        constraints = [
            models.UniqueConstraint(fields=["episode", "language"], name="unique_episode_language")
        ]

    def __str__(self):
        return f"{self.name} [{self.language}]"


# --- Per-user show state -----------------------------------------------------------------------


class UserSeries(models.Model):
    """What a user does with a show: following it, and whether they are watching it.

    Created when the user follows the show or marks the first episode as watched.
    """

    class Status(models.TextChoices):
        WATCHING = "watching", _("Watching")
        PAUSED = "paused", _("Paused")
        FINISHED = "finished", _("Finished")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="series",
    )
    # Named "title" like in WatchedMovie and ListItem, so lists can show these rows directly
    title = models.ForeignKey(
        Title,
        verbose_name=_("TV show"),
        on_delete=models.CASCADE,
        related_name="user_series",
        limit_choices_to={"media_type": MediaType.TV},
    )
    following = models.BooleanField(_("following"), default=False)
    followed_at = models.DateTimeField(_("followed since"), null=True, blank=True)
    # Empty until the first episode is marked as watched; used by the dashboard
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, blank=True)

    class Meta:
        verbose_name = _("user show")
        verbose_name_plural = _("user shows")
        constraints = [models.UniqueConstraint(fields=["user", "title"], name="unique_user_series")]

    def __str__(self):
        return f"{self.user} – {self.title}"


class WatchedEpisode(models.Model):
    """An episode the user has seen. Only the last date is kept (no history)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="watched_episodes",
    )
    episode = models.ForeignKey(
        Episode, verbose_name=_("episode"), on_delete=models.CASCADE, related_name="watched_by"
    )
    # Empty = seen, but the date is unknown
    watched_at = models.DateField(_("watched on"), null=True, blank=True)

    class Meta:
        verbose_name = _("watched episode")
        verbose_name_plural = _("watched episodes")
        constraints = [
            models.UniqueConstraint(fields=["user", "episode"], name="unique_watched_episode")
        ]

    def __str__(self):
        return f"{self.user} ✓ {self.episode}"
