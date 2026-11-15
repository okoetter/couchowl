"""Shows: following, watched episodes and progress. Views stay thin; the rules live here.

Rules (see docs/design.md):
- Only episodes that have aired (air date today or earlier) can be marked as watched.
- Progress and "next episode" ignore specials (season 0).
- A show counts as watched when all aired episodes (without specials) are watched.
- The next episode is the first unwatched aired episode, in season/episode order.
- The first watched episode of a show also follows it (see _start_watching).
"""

from dataclasses import dataclass
from datetime import date

from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.utils import timezone
from django.utils.translation import gettext as _

from . import services
from .models import (
    Episode,
    EpisodeTranslation,
    Season,
    SeasonTranslation,
    Title,
    UserSeries,
    WatchedEpisode,
)


@dataclass
class Progress:
    """How far a user is with a show (specials don't count)."""

    watched: int = 0
    aired: int = 0
    next_episode: Episode | None = None

    @property
    def complete(self) -> bool:
        return self.aired > 0 and self.watched >= self.aired

    @property
    def started(self) -> bool:
        return self.watched > 0


def _regular_aired(today: date, prefix: str = "") -> Q:
    """Filter for aired episodes outside of specials; `prefix` for related lookups."""
    return Q(**{f"{prefix}season__number__gt": 0, f"{prefix}air_date__lte": today})


# --- Following ---------------------------------------------------------------------------------


def is_following(user, show: Title) -> bool:
    return UserSeries.objects.filter(user=user, title=show, following=True).exists()


def set_following(user, show: Title, following: bool) -> None:
    series, _created = UserSeries.objects.get_or_create(user=user, title=show)
    if series.following != following:
        series.following = following
        series.followed_at = timezone.now() if following else None
        series.save(update_fields=["following", "followed_at"])


def followed_shows(user):
    """UserSeries rows of the followed shows, most recently followed first."""
    return (
        UserSeries.objects.filter(user=user, following=True)
        .select_related("title")
        .order_by("-followed_at", "-pk")
    )


# --- Marking episodes ----------------------------------------------------------------------------


def mark_episodes(
    user,
    episodes,
    watched_at=None,
    *,
    unknown_date=False,
    keep_existing=False,
    start_watching=True,
) -> list[Episode]:
    """Mark the aired ones of `episodes` as watched; returns those that were marked.

    Default date: today; `unknown_date` stores no date. `keep_existing` leaves episodes
    that are already watched (and their dates) alone, otherwise their date is replaced.
    `start_watching=False` skips the automatic follow on the first mark (batch import).
    """
    today = timezone.localdate()
    aired = [episode for episode in episodes if episode.has_aired(today)]
    if not aired:
        return []
    if unknown_date:
        watched_at = None
    elif watched_at is None:
        watched_at = today
    rows = [WatchedEpisode(user=user, episode=e, watched_at=watched_at) for e in aired]
    if keep_existing:
        WatchedEpisode.objects.bulk_create(rows, ignore_conflicts=True)
    else:
        WatchedEpisode.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["user", "episode"],
            update_fields=["watched_at"],
        )
    if start_watching:
        _start_watching(user, aired[0].season.show_id)
    return aired


def mark_episode(user, episode: Episode, watched_at=None, *, unknown_date=False) -> bool:
    """Mark one episode as watched (False if it hasn't aired yet)."""
    return bool(mark_episodes(user, [episode], watched_at, unknown_date=unknown_date))


def unwatched_before(user, season: Season, episode: Episode | None = None) -> list[Episode]:
    """Aired, unwatched episodes (without specials) before `episode`, or before `season`
    when no episode is given; in season/episode order.

    After marking an episode or season, the detail page offers to mark these too.
    """
    if season.is_specials:
        return []
    before = Q(season__number__lt=season.number)
    if episode is not None:
        before |= Q(season__number=season.number, number__lt=episode.number)
    return list(
        Episode.objects.filter(
            before, _regular_aired(timezone.localdate()), season__show_id=season.show_id
        )
        .exclude(watched_by__user=user)
        .select_related("season")
        .order_by("season__number", "number")
    )


def unmark_episodes(user, episodes) -> None:
    WatchedEpisode.objects.filter(user=user, episode__in=episodes).delete()


def mark_season(user, season: Season, watched_at=None, *, unknown_date=False, keep_existing=True):
    """Mark all aired episodes of a season. By default already watched ones keep their date."""
    episodes = list(season.episodes.select_related("season"))
    return mark_episodes(
        user, episodes, watched_at, unknown_date=unknown_date, keep_existing=keep_existing
    )


def unmark_season(user, season: Season) -> None:
    WatchedEpisode.objects.filter(user=user, episode__season=season).delete()


def _start_watching(user, show_id: int) -> None:
    """The first watched episode makes a show "currently watching" and follows it.

    Only the first time (status still empty): after an explicit "unfollow", watching more
    episodes doesn't follow the show again. Following puts it on the dashboard.
    """
    series, _created = UserSeries.objects.get_or_create(user=user, title_id=show_id)
    if not series.status:
        series.status = UserSeries.Status.WATCHING
        if not series.following:
            series.following = True
            series.followed_at = timezone.now()
        series.save(update_fields=["status", "following", "followed_at"])


def mark_show_watched(user, show: Title, *, follow: bool) -> list[Episode]:
    """Batch import: mark all aired episodes (without specials) as watched, date unknown.

    Already watched episodes keep their date. Unlike the first mark on the show page,
    this doesn't follow the show: the import's "Follow" checkbox decides (`follow`).
    The status still becomes "watching", so a later mark doesn't follow it either.
    """
    episodes = list(
        Episode.objects.filter(_regular_aired(timezone.localdate()), season__show=show)
        .select_related("season")
        .order_by("season__number", "number")
    )
    marked = mark_episodes(
        user, episodes, unknown_date=True, keep_existing=True, start_watching=False
    )
    if episodes:
        series, _created = UserSeries.objects.get_or_create(user=user, title=show)
        if not series.status:
            series.status = UserSeries.Status.WATCHING
            series.save(update_fields=["status"])
    if follow:
        set_following(user, show, True)
    return marked


def watch_next(user, show: Title) -> Episode | None:
    """Mark the next episode as watched (today) and return it; None if there is none."""
    episode = progress(user, [show])[show.pk].next_episode
    if episode is not None:
        mark_episode(user, episode)
    return episode


# --- Progress ------------------------------------------------------------------------------------


def progress(user, shows) -> dict[int, Progress]:
    """Progress per show (by Title pk), in a few queries for any number of shows."""
    show_ids = [show.pk for show in shows]
    today = timezone.localdate()
    aired = dict(
        Episode.objects.filter(_regular_aired(today), season__show__in=show_ids)
        .values_list("season__show")
        .annotate(count=Count("pk"))
    )
    watched = dict(
        WatchedEpisode.objects.filter(
            _regular_aired(today, "episode__"), user=user, episode__season__show__in=show_ids
        )
        .values_list("episode__season__show")
        .annotate(count=Count("pk"))
    )
    first_unwatched = (
        Episode.objects.filter(_regular_aired(today), season__show=OuterRef("pk"))
        .exclude(watched_by__user=user)
        .order_by("season__number", "number")
        .values("pk")[:1]
    )
    next_ids = dict(
        Title.objects.filter(pk__in=show_ids)
        .annotate(next_id=Subquery(first_unwatched))
        .values_list("pk", "next_id")
    )
    next_episodes = Episode.objects.select_related("season").in_bulk(
        [pk for pk in next_ids.values() if pk]
    )
    return {
        show_id: Progress(
            watched=watched.get(show_id, 0),
            aired=aired.get(show_id, 0),
            next_episode=next_episodes.get(next_ids.get(show_id)),
        )
        for show_id in show_ids
    }


def watched_show_ids(user, tmdb_ids) -> set[int]:
    """TMDB IDs of the given shows that `user` has completely watched (e.g. for search)."""
    shows = list(Title.objects.filter(media_type="tv", tmdb_id__in=list(tmdb_ids)))
    done = progress(user, shows)
    return {show.tmdb_id for show in shows if done[show.pk].complete}


# --- Detail page ---------------------------------------------------------------------------------


def seasons_overview(user, show: Title, language: str) -> list[Season]:
    """All seasons of a show for the detail page, specials last.

    Each season gets: `name`, `overview`, `episode_count`, `aired_count`, `watched_count`,
    `last_watched` (date of the last watched episode), `complete` and `started`.
    """
    today = timezone.localdate()
    mine = Q(episodes__watched_by__user=user)
    seasons = list(
        show.seasons.annotate(
            episode_count=Count("episodes", distinct=True),
            aired_count=Count("episodes", filter=Q(episodes__air_date__lte=today), distinct=True),
            watched_count=Count("episodes__watched_by", filter=mine, distinct=True),
            last_watched=Max("episodes__watched_by__watched_at", filter=mine),
        )
    )
    texts = services.best_texts(
        SeasonTranslation.objects.filter(season__in=seasons), language, owner="season_id"
    )
    for season in seasons:
        text = texts.get(season.pk)
        season.name = (text.name if text else "") or default_season_name(season)
        season.overview = text.overview if text else ""
        season.complete = season.aired_count > 0 and season.watched_count >= season.aired_count
        season.started = season.watched_count > 0
    return sorted(seasons, key=lambda season: (season.is_specials, season.number))


def default_season_name(season: Season) -> str:
    if season.is_specials:
        return _("Specials")
    return _("Season %(number)s") % {"number": season.number}


def season_episodes(user, season: Season, language: str) -> list[Episode]:
    """Episodes of a season with `name`, `overview`, `aired` and `watched` (row or None)."""
    today = timezone.localdate()
    episodes = list(season.episodes.select_related("season"))
    texts = services.best_texts(
        EpisodeTranslation.objects.filter(episode__season=season), language, owner="episode_id"
    )
    watched = {
        row.episode_id: row
        for row in WatchedEpisode.objects.filter(user=user, episode__season=season)
    }
    for episode in episodes:
        text = texts.get(episode.pk)
        episode.name = (text.name if text else "") or _("Episode %(number)s") % {
            "number": episode.number
        }
        episode.overview = text.overview if text else ""
        episode.aired = episode.has_aired(today)
        episode.watched = watched.get(episode.pk)
    return episodes


def episode_names(episodes, language: str) -> dict[int, str]:
    """Stored names of `episodes` in (or closest to) `language`, by episode pk."""
    texts = services.best_texts(
        EpisodeTranslation.objects.filter(episode__in=episodes), language, owner="episode_id"
    )
    return {pk: text.name for pk, text in texts.items() if text.name}
