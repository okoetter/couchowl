"""Dashboard rules: "continue watching" and announcements of new seasons."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from catalog import dashboard, services, shows
from catalog.models import Episode, Season, UserSeries
from conftest import dark_seasons, load_tmdb_fixture


def episode(show, season, number):
    return Episode.objects.select_related("season").get(
        season__show=show, season__number=season, number=number
    )


def another_show(tmdb_id=1, name="Another show"):
    """A copy of "Dark" under another id and name."""
    data = load_tmdb_fixture("tv_70523")
    data.update(id=tmdb_id, original_name=name, networks=[])
    for translation in data["translations"]["translations"]:
        translation["data"]["name"] = ""
    return services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title


def starts_in(show, number, days):
    """Let season `number` of `show` start `days` from today (its episodes later)."""
    start = timezone.localdate() + timedelta(days=days)
    Season.objects.filter(show=show, number=number).update(air_date=start)
    Episode.objects.filter(season__show=show, season__number=number).update(air_date=start)


@pytest.mark.parametrize(
    ("day", "months", "expected"),
    [
        (date(2026, 11, 8), 3, date(2027, 2, 8)),
        (date(2026, 11, 30), 3, date(2027, 2, 28)),
        (date(2027, 11, 30), 3, date(2028, 2, 29)),  # leap year
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2026, 5, 15), 12, date(2027, 5, 15)),
        (date(2026, 5, 15), 0, date(2026, 5, 15)),
    ],
)
def test_add_months(day, months, expected):
    assert dashboard.add_months(day, months) == expected


# --- Continue watching -------------------------------------------------------------------------


def test_watching_show_appears_with_next_episode(user, show):
    shows.mark_episode(user, episode(show, 1, 1))

    [entry] = dashboard.continue_watching(user, "de-DE")

    assert entry.show == show
    assert entry.name == "Dark"
    assert entry.next_episode == episode(show, 1, 2)
    assert entry.next_name == "Lügen"
    assert (entry.progress.watched, entry.progress.aired) == (1, 26)


def test_followed_but_not_started_show_is_not_shown(user, show):
    shows.set_following(user, show, True)

    assert dashboard.continue_watching(user, "de-DE") == []


def test_unfollowed_show_is_not_shown(user, show):
    shows.mark_episode(user, episode(show, 1, 1))
    shows.set_following(user, show, False)

    assert dashboard.continue_watching(user, "de-DE") == []


def test_caught_up_show_is_not_shown(user, show):
    for number in (1, 2, 3):
        shows.mark_season(user, show.seasons.get(number=number))

    assert dashboard.continue_watching(user, "de-DE") == []
    # Still "watching": it comes back when a new episode has aired
    assert UserSeries.objects.get(user=user, title=show).status == UserSeries.Status.WATCHING


def test_show_without_watched_episodes_is_not_shown(user, show):
    first = episode(show, 1, 1)
    shows.mark_episode(user, first)
    shows.unmark_episodes(user, [first])

    assert dashboard.continue_watching(user, "de-DE") == []


def test_only_specials_watched_is_not_shown(user, show):
    shows.mark_episode(user, episode(show, 0, 1))

    assert dashboard.continue_watching(user, "de-DE") == []


@pytest.mark.parametrize("status", [UserSeries.Status.PAUSED, UserSeries.Status.FINISHED])
def test_paused_and_finished_shows_are_not_shown(user, show, status):
    shows.mark_episode(user, episode(show, 1, 1))
    UserSeries.objects.filter(user=user, title=show).update(status=status)

    assert dashboard.continue_watching(user, "de-DE") == []


def test_most_recently_watched_show_comes_first(user, show):
    other = another_show()
    shows.mark_episode(user, episode(show, 1, 1), date(2024, 5, 1))
    shows.mark_episode(user, episode(other, 1, 1), date(2024, 1, 1))

    assert [e.show for e in dashboard.continue_watching(user, "de-DE")] == [show, other]

    shows.mark_episode(user, episode(other, 1, 2), date(2024, 6, 1))

    assert [e.show for e in dashboard.continue_watching(user, "de-DE")] == [other, show]


def test_unknown_dates_count_as_oldest_then_last_marked_first(user, show):
    other = another_show()
    shows.mark_episode(user, episode(show, 1, 1), unknown_date=True)
    shows.mark_episode(user, episode(other, 1, 1), unknown_date=True)

    assert [e.show for e in dashboard.continue_watching(user, "de-DE")] == [other, show]


def test_other_users_shows_are_not_shown(user, other_user, show):
    shows.mark_episode(other_user, episode(show, 1, 1))

    assert dashboard.continue_watching(user, "de-DE") == []


def test_continue_watching_uses_few_queries(user, show, django_assert_max_num_queries):
    for tmdb_id in (1, 2, 3):
        shows.mark_episode(user, episode(another_show(tmdb_id), 1, 1))
    shows.mark_episode(user, episode(show, 1, 1))

    with django_assert_max_num_queries(10):
        entries = dashboard.continue_watching(user, "de-DE")
        [(e.name, e.next_episode.code) for e in entries]

    assert len(entries) == 4


# --- Announcements -------------------------------------------------------------------------------


def test_upcoming_season_of_followed_show_is_announced(user, show):
    shows.set_following(user, show, True)
    starts_in(show, 3, 10)

    [announcement] = dashboard.announcements(user, "de-DE")

    assert announcement.show == show
    assert announcement.name == "Dark"
    assert announcement.season.number == 3
    assert announcement.season_name == "Staffel 3"
    assert announcement.days_until == 10
    assert announcement.show.networks == ["Netflix"]


def test_season_starting_today_is_announced(user, show):
    shows.set_following(user, show, True)
    starts_in(show, 3, 0)

    [announcement] = dashboard.announcements(user, "de-DE")

    assert announcement.days_until == 0


def test_seasons_of_shows_that_are_not_followed_are_not_announced(user, other_user, show):
    shows.set_following(other_user, show, True)
    shows.mark_episode(user, episode(show, 1, 1))
    shows.set_following(user, show, False)  # watching, but not following
    starts_in(show, 3, 10)

    assert dashboard.announcements(user, "de-DE") == []


def test_past_seasons_and_specials_are_not_announced(user, show):
    shows.set_following(user, show, True)
    starts_in(show, 0, 10)

    assert dashboard.announcements(user, "de-DE") == []


def test_announcement_window_comes_from_settings(user, show, settings):
    shows.set_following(user, show, True)
    starts_in(show, 3, 40)

    settings.ANNOUNCEMENT_MONTHS = 1
    assert dashboard.announcements(user, "de-DE") == []

    settings.ANNOUNCEMENT_MONTHS = 2
    assert [a.season.number for a in dashboard.announcements(user, "de-DE")] == [3]


def test_last_day_of_the_window_is_included(user, show, settings):
    settings.ANNOUNCEMENT_MONTHS = 3
    shows.set_following(user, show, True)
    today = timezone.localdate()
    starts_in(show, 3, (dashboard.add_months(today, 3) - today).days)
    starts_in(show, 2, (dashboard.add_months(today, 3) - today).days + 1)

    assert [a.season.number for a in dashboard.announcements(user, "de-DE")] == [3]


def test_announcements_are_sorted_by_date(user, show):
    other = another_show()
    for followed in (show, other):
        shows.set_following(user, followed, True)
    starts_in(show, 3, 30)
    starts_in(other, 2, 5)

    result = dashboard.announcements(user, "de-DE")

    assert [(a.show, a.season.number) for a in result] == [(other, 2), (show, 3)]
    assert result[0].name == "Another show"


def test_season_without_stored_name_gets_a_default_name(user, show):
    shows.set_following(user, show, True)
    starts_in(show, 3, 10)
    show.seasons.get(number=3).translations.all().delete()

    # Translated default name (tests run in German)
    assert dashboard.announcements(user, "de-DE")[0].season_name == "Staffel 3"


def test_season_starts_with_its_first_episode(user, show):
    # TMDB's season date can be a day earlier than the first episode
    shows.set_following(user, show, True)
    starts_in(show, 3, 10)
    Season.objects.filter(show=show, number=3).update(
        air_date=timezone.localdate() + timedelta(days=9)
    )

    [announcement] = dashboard.announcements(user, "de-DE")

    assert announcement.starts == timezone.localdate() + timedelta(days=10)
    assert announcement.days_until == 10


def test_season_date_counts_when_no_episode_has_a_date(user, show):
    shows.set_following(user, show, True)
    starts_in(show, 3, 10)
    Episode.objects.filter(season__show=show, season__number=3).update(air_date=None)

    [announcement] = dashboard.announcements(user, "de-DE")

    assert announcement.days_until == 10


def test_season_with_aired_first_episode_is_not_announced(user, show):
    # Already running: the first episode aired yesterday, the season date is in the future
    shows.set_following(user, show, True)
    starts_in(show, 3, 10)
    Episode.objects.filter(season__show=show, season__number=3, number=1).update(
        air_date=timezone.localdate() - timedelta(days=1)
    )

    assert dashboard.announcements(user, "de-DE") == []
