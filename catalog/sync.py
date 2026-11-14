"""Reloading shows from TMDB in bulk: the daily sync and the "Refresh all" button.

Rules (see docs/design.md):
- The daily sync (`manage.py sync_tmdb`) reloads every show that someone follows or is
  watching, in the TMDB languages of those users: details, seasons, episodes, air dates and
  streaming providers. Shows loaded recently (MAX_AGE) are skipped, e.g. when someone
  opened them shortly before.
- "Refresh all" (page "Upcoming") reloads the shows the user follows, in their language.
  Ended and canceled shows are skipped there: they get no new dates.
- An error with one show doesn't stop the others.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from . import services, tmdb
from .models import MediaType, Title, TitleTranslation, UserSeries

logger = logging.getLogger(__name__)

# The daily sync skips shows that were loaded within this time
MAX_AGE = timedelta(hours=6)
# TMDB status of shows that won't get new seasons
FINISHED_STATUSES = ("Ended", "Canceled")


@dataclass
class SyncResult:
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def shows_to_sync() -> dict[Title, set[str]]:
    """Shows that someone follows or is watching, with the TMDB languages of those users."""
    active = Q(following=True) | Q(status=UserSeries.Status.WATCHING)
    languages: dict[Title, set[str]] = defaultdict(set)
    for series in UserSeries.objects.filter(active).select_related("title", "user"):
        languages[series.title].add(series.user.effective_tmdb_language)
    return dict(languages)


def sync_shows(*, max_age: timedelta | None = MAX_AGE, progress=None) -> SyncResult:
    """Reload all shows from shows_to_sync(). `max_age=None` reloads even fresh ones.

    `progress(message)` is called after every show (for the command's output).
    Raises tmdb.TMDBNotConfigured if there is no TMDB token.
    """
    tmdb.get_client()  # fail early without a token, even if every show is fresh
    result = SyncResult()
    targets = sorted(shows_to_sync().items(), key=lambda item: item[0].original_title.casefold())
    for show, languages in targets:
        message = _refresh(show, languages, max_age, result)
        if progress:
            progress(message)
    return result


def refresh_followed(user) -> SyncResult:
    """ "Refresh all": reload the shows `user` follows (not ended ones) in their language."""
    result = SyncResult()
    shows = (
        Title.objects.filter(user_series__user=user, user_series__following=True)
        .exclude(status__in=FINISHED_STATUSES)
        .order_by("original_title")
    )
    for show in shows:
        _refresh(show, {user.effective_tmdb_language}, None, result)
    return result


def _refresh(show: Title, languages: set[str], max_age, result: SyncResult) -> str:
    """Reload `show` in each of `languages`; record the outcome in `result`."""
    name = f"{show.original_title} ({show.tmdb_id})"
    if max_age is not None and _is_fresh(show, languages, max_age):
        result.skipped.append(name)
        return f"{name}: skipped (loaded recently)"
    try:
        for language in sorted(languages):
            services.fetch_title(MediaType.TV, show.tmdb_id, language)
    except tmdb.TMDBNotConfigured:
        raise
    except tmdb.TMDBNotFound:
        # Removed from TMDB: keep the stored data, the user can still see what they watched
        logger.warning("Show %s no longer exists on TMDB", name)
        result.failed.append(name)
        return f"{name}: not found on TMDB"
    except tmdb.TMDBError as error:
        logger.warning("Could not sync %s: %s", name, error)
        result.failed.append(name)
        return f"{name}: failed ({error})"
    result.updated.append(name)
    return f"{name}: updated"


def _is_fresh(show: Title, languages: set[str], max_age: timedelta) -> bool:
    """All `languages` of `show` were loaded within `max_age`, with providers of all
    our regions (a new user's region would be missing otherwise)."""
    since = timezone.now() - max_age
    fresh = TitleTranslation.objects.filter(
        title=show, language__in=languages, fetched_at__gte=since
    ).count()
    return fresh == len(languages) and services.provider_regions() <= show.watch_providers.keys()
