from datetime import date

from catalog import lists, reset, shows
from catalog.models import ListItem, Title, UserSeries, WatchedEpisode, WatchedMovie


def fill(user, movie, show):
    """A list with two titles, a watched movie, watched episodes and a followed show."""
    watchlist = user.lists.create(name="Watchlist")
    lists.add_to_list(watchlist, movie)
    lists.add_to_list(watchlist, show)
    user.lists.create(name="Empty")
    lists.mark_watched(user, movie, date(2024, 3, 1))
    shows.mark_season(user, show.seasons.get(number=1))  # follows the show automatically


def test_user_data_counts_what_would_be_lost(user, movie, show):
    fill(user, movie, show)

    data = reset.user_data(user)

    assert data == reset.UserData(
        lists=2,
        watched_movies=1,
        watched_episodes=show.seasons.get(number=1).episodes.count(),
        followed_shows=1,
    )
    assert not data.is_empty


def test_unfollowed_shows_are_not_counted_as_followed(user, show):
    shows.mark_episode(user, show.seasons.get(number=1).episodes.first())
    shows.set_following(user, show, False)

    assert reset.user_data(user).followed_shows == 0


def test_new_user_has_nothing_to_reset(user):
    assert reset.user_data(user).is_empty


def test_reset_deletes_all_own_data(user, movie, show):
    fill(user, movie, show)
    shows.set_following(user, show, False)  # an unfollowed show keeps its status otherwise

    reset.reset_user_data(user)

    assert reset.user_data(user).is_empty
    assert not ListItem.objects.exists()
    assert not UserSeries.objects.exists()


def test_reset_keeps_account_settings_and_titles(user, movie, show):
    user.theme = "dark"
    user.save()
    fill(user, movie, show)

    reset.reset_user_data(user)

    user.refresh_from_db()
    assert user.theme == "dark"
    assert Title.objects.count() == 2
    assert show.seasons.exists()


def test_reset_leaves_other_users_alone(user, other_user, movie, show):
    fill(user, movie, show)
    fill(other_user, movie, show)

    reset.reset_user_data(user)

    assert reset.user_data(other_user) == reset.UserData(
        lists=2,
        watched_movies=1,
        watched_episodes=show.seasons.get(number=1).episodes.count(),
        followed_shows=1,
    )
    assert WatchedMovie.objects.filter(user=other_user).exists()
    assert WatchedEpisode.objects.filter(user=other_user).exists()


def test_first_mark_after_reset_follows_again(user, show):
    episode = show.seasons.get(number=1).episodes.first()
    shows.mark_episode(user, episode)
    shows.set_following(user, show, False)

    reset.reset_user_data(user)
    shows.mark_episode(user, episode)

    assert shows.is_following(user, show)
