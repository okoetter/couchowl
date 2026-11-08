"""Dashboard: shows the user is watching, and announced seasons of followed shows.

Like lists, the dashboard only reads the database and never asks TMDB (new seasons and
air dates arrive when a show is loaded again, later also via the daily sync).

Rules (see docs/KONZEPT.md):
- "Continue watching": followed shows with status "watching" that have a next episode (the
  first unwatched aired one, see catalog.shows) and at least one watched episode.
  Unfollowing removes a show the user doesn't want to continue. Most recently
  watched first. Caught-up shows stay while their current season is running ("waiting"):
  the next episode of a season that has already started airs later. They show its date
  instead of the check button and come after the others, soonest first. A season that
  hasn't started yet is an announcement instead.
- "Announcements": seasons (without specials) of followed shows that start between today
  and ANNOUNCEMENT_MONTHS months from now, soonest first. A season starts with its first
  episode (like on the show page); TMDB's season date only counts if no episode has a date
  (both can differ by a day).
- "Upcoming" (own page): like the announcements without time limit, plus the next episode
  of each running season.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date

from django.conf import settings
from django.db.models import Exists, Max, Min, OuterRef
from django.db.models.functions import Coalesce
from django.utils import timezone

from . import providers, services, shows
from .models import (
    Episode,
    Season,
    SeasonTranslation,
    Title,
    TitleTranslation,
    UserSeries,
    WatchedEpisode,
)


@dataclass
class WatchingEntry:
    """A show on the dashboard with its next episode."""

    show: Title
    translation: TitleTranslation | None
    progress: shows.Progress
    next_name: str = ""
    waiting_for: Episode | None = None  # caught up: the next episode airs later

    @property
    def name(self) -> str:
        return self.translation.name if self.translation else self.show.original_title

    @property
    def next_episode(self) -> Episode:
        return self.progress.next_episode or self.waiting_for

    @property
    def days_until(self) -> int | None:
        """Days until the episode the user is waiting for airs."""
        if self.waiting_for is None:
            return None
        return (self.waiting_for.air_date - timezone.localdate()).days


@dataclass
class Announcement:
    """A season of a followed show that starts soon, or (page "Upcoming") the next episode
    of a season that is already running."""

    season: Season
    season_name: str
    translation: TitleTranslation | None
    starts: date
    days_until: int
    sources: list[str] = field(default_factory=list)  # networks and streaming providers
    episode: Episode | None = None
    episode_name: str = ""

    @property
    def show(self) -> Title:
        return self.season.show

    @property
    def name(self) -> str:
        return self.translation.name if self.translation else self.show.original_title

    @property
    def month(self) -> date:
        """First day of the month, for grouping on the page "Upcoming"."""
        return self.starts.replace(day=1)


def add_months(day: date, months: int) -> date:
    """Same day `months` later; the 31st becomes the last day of shorter months."""
    years, month_index = divmod(day.month - 1 + months, 12)
    year, month = day.year + years, month_index + 1
    last_day = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last_day))


def continue_watching(user, language: str) -> list[WatchingEntry]:
    """Followed shows the user is watching: those with a next episode (most recently
    watched first), then caught-up shows waiting for the next episode of a running season
    (soonest first)."""
    show_list = [
        series.title
        for series in UserSeries.objects.filter(
            user=user, following=True, status=UserSeries.Status.WATCHING
        ).select_related("title")
    ]
    progress = shows.progress(user, show_list)
    started = [show for show in show_list if progress[show.pk].started]
    ready = [show for show in started if progress[show.pk].next_episode is not None]
    waiting_for = _waiting_for(
        user, [show for show in started if progress[show.pk].next_episode is None]
    )
    if not ready and not waiting_for:
        return []

    # Last activity per show: latest watched date, then the most recently marked episode
    activity = {
        row["episode__season__show"]: (row["last_date"] or date.min, row["last_pk"])
        for row in WatchedEpisode.objects.filter(user=user, episode__season__show__in=ready)
        .values("episode__season__show")
        .annotate(last_date=Max("watched_at"), last_pk=Max("pk"))
    }
    ready.sort(key=lambda show: activity.get(show.pk, (date.min, 0)), reverse=True)
    waiting = sorted(
        (show for show in started if show.pk in waiting_for),
        key=lambda show: (waiting_for[show.pk].air_date, show.original_title.casefold()),
    )
    show_list = ready + waiting

    translations = services.best_translations(show_list, language)
    next_episodes = [progress[s.pk].next_episode or waiting_for[s.pk] for s in show_list]
    next_names = shows.episode_names(next_episodes, language)
    return [
        WatchingEntry(
            show=show,
            translation=translations.get(show.pk),
            progress=progress[show.pk],
            next_name=next_names.get(next_episode.pk, ""),
            waiting_for=waiting_for.get(show.pk),
        )
        for show, next_episode in zip(show_list, next_episodes, strict=True)
    ]


def _waiting_for(user, caught_up) -> dict[int, Episode]:
    """Per caught-up show (by Title pk): the next unwatched episode of a season that has
    already started (it has an aired episode) but airs later. No date, no entry."""
    if not caught_up:
        return {}
    today = timezone.localdate()
    aired_in_season = Episode.objects.filter(season=OuterRef("season"), air_date__lte=today)
    episodes = (
        Episode.objects.filter(
            Exists(aired_in_season),
            season__show__in=caught_up,
            season__number__gt=0,
            air_date__gt=today,
        )
        .exclude(watched_by__user=user)
        .select_related("season")
        .order_by("season__number", "number")
    )
    result: dict[int, Episode] = {}
    for episode in episodes:
        result.setdefault(episode.season.show_id, episode)
    return result


def announcements(user, language: str, months: int | None = None) -> list[Announcement]:
    """Seasons of followed shows starting within `months` (default ANNOUNCEMENT_MONTHS)."""
    today = timezone.localdate()
    until = add_months(today, settings.ANNOUNCEMENT_MONTHS if months is None else months)
    return _season_starts(user, language, today, until)


def upcoming(user, language: str) -> list[Announcement]:
    """Page "Upcoming": all known season starts of followed shows (no time limit), plus the
    next episode of each running season; soonest first.

    A season is running when it started before today and still has episodes with a date
    ahead. Seasons that start today or later appear only once (with their start).
    """
    today = timezone.localdate()
    entries = _season_starts(user, language, today, None) + _next_episodes(user, language, today)
    entries.sort(
        key=lambda a: (
            a.starts,
            a.name.casefold(),
            a.season.number,
            a.episode.number if a.episode else 0,
        )
    )
    return entries


def _followed_seasons(user):
    return Season.objects.filter(
        show__user_series__user=user, show__user_series__following=True, number__gt=0
    ).annotate(starts=Coalesce(Min("episodes__air_date"), "air_date"))


def _season_starts(user, language: str, today: date, until: date | None) -> list[Announcement]:
    """Seasons of followed shows starting between `today` and `until` (None = any time)."""
    seasons = _followed_seasons(user).filter(starts__gte=today)
    if until is not None:
        seasons = seasons.filter(starts__lte=until)
    seasons = list(
        seasons.select_related("show").order_by("starts", "show__original_title", "number")
    )
    return _announcements(user, language, today, [(season, None) for season in seasons])


def _next_episodes(user, language: str, today: date) -> list[Announcement]:
    """The next episode (air date today or later) of each running season."""
    ahead = Episode.objects.filter(season=OuterRef("pk"), air_date__gte=today)
    running = list(_followed_seasons(user).filter(Exists(ahead), starts__lt=today))
    episodes = (
        Episode.objects.filter(season__in=running, air_date__gte=today)
        .select_related("season__show")
        .order_by("air_date", "number")
    )
    first: dict[int, Episode] = {}
    for episode in episodes:
        first.setdefault(episode.season_id, episode)
    return _announcements(
        user, language, today, [(episode.season, episode) for episode in first.values()]
    )


def _announcements(user, language: str, today: date, items) -> list[Announcement]:
    """Announcement objects with texts for (season, episode or None) pairs."""
    seasons = [season for season, _episode in items]
    show_list = [season.show for season in seasons]
    translations = services.best_translations(show_list, language)
    texts = services.best_texts(
        SeasonTranslation.objects.filter(season__in=seasons), language, owner="season_id"
    )
    episode_names = shows.episode_names([e for _s, e in items if e is not None], language)
    region = user.effective_region
    result = []
    for season, episode in items:
        text = texts.get(season.pk)
        starts = episode.air_date if episode else season.starts
        result.append(
            Announcement(
                season=season,
                season_name=(text.name if text else "") or shows.default_season_name(season),
                translation=translations.get(season.show_id),
                starts=starts,
                days_until=(starts - today).days,
                sources=providers.sources(season.show, region),
                episode=episode,
                episode_name=episode_names.get(episode.pk, "") if episode else "",
            )
        )
    return result
