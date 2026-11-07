"""Lists and "watched" state of a user. Views stay thin; the rules live here."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import ListItem, Title, UserList, WatchedMovie


def lists_for_title(user, title: Title | None) -> list[UserList]:
    """All lists of `user`; each gets `.contains` = whether `title` is on it."""
    lists = list(user.lists.all())
    member_of = set()
    if title is not None:
        member_of = set(
            ListItem.objects.filter(user_list__user=user, title=title).values_list(
                "user_list_id", flat=True
            )
        )
    for user_list in lists:
        user_list.contains = user_list.pk in member_of
    return lists


def find_or_create_list(user, name: str) -> UserList:
    """The user's list called `name` (ignoring case), created if it doesn't exist."""
    name = " ".join(name.split())
    existing = user.lists.filter(name__iexact=name).first()
    if existing:
        return existing
    try:
        with transaction.atomic():
            return user.lists.create(name=name)
    except IntegrityError:  # created at the same moment by another request
        return user.lists.get(name__iexact=name)


def add_to_list(user_list: UserList, title: Title) -> None:
    """Add `title`; adding it a second time changes nothing."""
    ListItem.objects.get_or_create(user_list=user_list, title=title)


def remove_from_list(user_list: UserList, title: Title) -> None:
    ListItem.objects.filter(user_list=user_list, title=title).delete()


# --- Watched movies ------------------------------------------------------------------------


def mark_watched(user, movie: Title, watched_at=None, *, unknown_date=False) -> WatchedMovie:
    """Mark a movie as watched. Default date: today; `unknown_date` stores no date.

    Watching again simply replaces the date (only the last date is kept).
    """
    if not unknown_date and watched_at is None:
        watched_at = timezone.localdate()
    watched, _created = WatchedMovie.objects.update_or_create(
        user=user, title=movie, defaults={"watched_at": None if unknown_date else watched_at}
    )
    return watched


def unmark_watched(user, movie: Title) -> None:
    WatchedMovie.objects.filter(user=user, title=movie).delete()


def watched_movie_ids(user, tmdb_ids) -> set[int]:
    """TMDB IDs of the given movies that `user` has watched (e.g. for search results)."""
    return set(
        WatchedMovie.objects.filter(
            user=user, title__media_type="movie", title__tmdb_id__in=list(tmdb_ids)
        ).values_list("title__tmdb_id", flat=True)
    )
