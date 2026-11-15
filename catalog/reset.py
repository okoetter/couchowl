"""Deleting all of a user's own data ("Reset my data" in the profile), to start over.

Lists, watched movies and episodes, follows and show statuses are deleted. The account,
its settings and the TMDB data (titles are shared by all users) stay.
"""

from dataclasses import dataclass

from django.db import transaction

from .models import UserList, UserSeries, WatchedEpisode, WatchedMovie


@dataclass(frozen=True)
class UserData:
    """How much would be lost; shown before the user confirms."""

    lists: int
    watched_movies: int
    watched_episodes: int
    followed_shows: int

    @property
    def is_empty(self) -> bool:
        return not (
            self.lists or self.watched_movies or self.watched_episodes or self.followed_shows
        )


def user_data(user) -> UserData:
    return UserData(
        lists=UserList.objects.filter(user=user).count(),
        watched_movies=WatchedMovie.objects.filter(user=user).count(),
        watched_episodes=WatchedEpisode.objects.filter(user=user).count(),
        followed_shows=UserSeries.objects.filter(user=user, following=True).count(),
    )


def reset_user_data(user) -> None:
    """Delete everything the user has entered. Can't be undone."""
    # transaction.atomic: all or nothing, never half a reset
    with transaction.atomic():
        UserList.objects.filter(user=user).delete()  # list entries are deleted with their list
        WatchedMovie.objects.filter(user=user).delete()
        WatchedEpisode.objects.filter(user=user).delete()
        # All rows, not only followed shows: the status ("watching") goes too, so the
        # first mark after the reset follows a show again
        UserSeries.objects.filter(user=user).delete()
