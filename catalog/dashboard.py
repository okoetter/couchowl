"""Dashboard: shows the user is watching, and announced seasons of followed shows.

Like lists, the dashboard only reads the database and never asks TMDB (new seasons and
air dates arrive when a show is loaded again, later also via the daily sync).

Rules (see docs/KONZEPT.md):
- "Continue watching": followed shows with status "watching" that have a next episode (the
  first unwatched aired one, see catalog.shows) and at least one watched episode.
  Unfollowing removes a show the user doesn't want to continue. Most recently
  watched first. Caught-up shows disappear until a new episode has aired.
- "Announcements": seasons (without specials) of followed shows that start between today
  and ANNOUNCEMENT_MONTHS months from now, soonest first. A season starts with its first
  episode (like on the show page); TMDB's season date only counts if no episode has a date
  (both can differ by a day).
"""

import calendar
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.db.models import Max, Min
from django.db.models.functions import Coalesce
from django.utils import timezone

from . import services, shows
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

    @property
    def name(self) -> str:
        return self.translation.name if self.translation else self.show.original_title

    @property
    def next_episode(self) -> Episode:
        return self.progress.next_episode


@dataclass
class Announcement:
    """A season of a followed show that starts soon."""

    season: Season
    season_name: str
    translation: TitleTranslation | None
    starts: date
    days_until: int

    @property
    def show(self) -> Title:
        return self.season.show

    @property
    def name(self) -> str:
        return self.translation.name if self.translation else self.show.original_title


def add_months(day: date, months: int) -> date:
    """Same day `months` later; the 31st becomes the last day of shorter months."""
    years, month_index = divmod(day.month - 1 + months, 12)
    year, month = day.year + years, month_index + 1
    last_day = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last_day))


def continue_watching(user, language: str) -> list[WatchingEntry]:
    """Followed shows the user is watching that have a next episode, most recently watched
    first."""
    show_list = [
        series.title
        for series in UserSeries.objects.filter(
            user=user, following=True, status=UserSeries.Status.WATCHING
        ).select_related("title")
    ]
    progress = shows.progress(user, show_list)
    show_list = [
        show
        for show in show_list
        if progress[show.pk].started and progress[show.pk].next_episode is not None
    ]
    if not show_list:
        return []

    # Last activity per show: latest watched date, then the most recently marked episode
    activity = {
        row["episode__season__show"]: (row["last_date"] or date.min, row["last_pk"])
        for row in WatchedEpisode.objects.filter(user=user, episode__season__show__in=show_list)
        .values("episode__season__show")
        .annotate(last_date=Max("watched_at"), last_pk=Max("pk"))
    }
    show_list.sort(key=lambda show: activity.get(show.pk, (date.min, 0)), reverse=True)

    translations = services.best_translations(show_list, language)
    next_names = shows.episode_names([progress[s.pk].next_episode for s in show_list], language)
    return [
        WatchingEntry(
            show=show,
            translation=translations.get(show.pk),
            progress=progress[show.pk],
            next_name=next_names.get(progress[show.pk].next_episode.pk, ""),
        )
        for show in show_list
    ]


def announcements(user, language: str, months: int | None = None) -> list[Announcement]:
    """Seasons of followed shows starting within `months` (default ANNOUNCEMENT_MONTHS)."""
    today = timezone.localdate()
    until = add_months(today, settings.ANNOUNCEMENT_MONTHS if months is None else months)
    seasons = list(
        Season.objects.filter(
            show__user_series__user=user, show__user_series__following=True, number__gt=0
        )
        .annotate(starts=Coalesce(Min("episodes__air_date"), "air_date"))
        .filter(starts__gte=today, starts__lte=until)
        .select_related("show")
        .order_by("starts", "show__original_title", "number")
    )
    translations = services.best_translations([season.show for season in seasons], language)
    texts = services.best_texts(
        SeasonTranslation.objects.filter(season__in=seasons), language, owner="season_id"
    )
    result = []
    for season in seasons:
        text = texts.get(season.pk)
        result.append(
            Announcement(
                season=season,
                season_name=(text.name if text else "") or shows.default_season_name(season),
                translation=translations.get(season.show_id),
                starts=season.starts,
                days_until=(season.starts - today).days,
            )
        )
    return result
