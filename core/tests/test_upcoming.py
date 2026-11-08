"""Page "Upcoming": season starts and next episodes of followed shows."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import formats, timezone

from accounts.models import User
from catalog import dashboard, services, shows
from catalog.models import Episode, Season
from conftest import dark_seasons, load_tmdb_fixture


@pytest.fixture
def show(db):
    data = load_tmdb_fixture("tv_70523")
    return services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title


def another_show(tmdb_id, name):
    data = load_tmdb_fixture("tv_70523")
    data.update(id=tmdb_id, original_name=name, networks=[])
    for translation in data["translations"]["translations"]:
        translation["data"]["name"] = ""
    return services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title


def day(offset):
    return timezone.localdate() + timedelta(days=offset)


def season_starts(show, number, offset):
    """Season `number` starts `offset` days from today, one episode per week."""
    Season.objects.filter(show=show, number=number).update(air_date=day(offset))
    for episode in Episode.objects.filter(season__show=show, season__number=number):
        episode.air_date = day(offset + 7 * (episode.number - 1))
        episode.save()


def describe(entries):
    return [
        (e.show.original_title, e.season.number, e.episode.number if e.episode else None, e.starts)
        for e in entries
    ]


# --- Rules --------------------------------------------------------------------------------------


def test_season_starts_without_time_limit(user, show):
    shows.set_following(user, show, True)
    season_starts(show, 3, 400)

    [entry] = dashboard.upcoming(user, "de-DE")

    assert describe([entry]) == [("Dark", 3, None, day(400))]
    assert entry.season_name == "Staffel 3"
    # Not within the dashboard's 3 months
    assert dashboard.announcements(user, "de-DE") == []


def test_running_season_shows_its_next_episode(user, show):
    shows.set_following(user, show, True)
    season_starts(show, 3, -10)  # E1 10 days ago, E2 3 days ago, E3 in 4 days, …

    [entry] = dashboard.upcoming(user, "de-DE")

    assert describe([entry]) == [("Dark", 3, 3, day(4))]
    assert entry.episode_name == "Adam und Eva"
    assert entry.days_until == 4


def test_episode_airing_today_is_upcoming(user, show):
    shows.set_following(user, show, True)
    season_starts(show, 3, -7)

    [entry] = dashboard.upcoming(user, "de-DE")

    assert (entry.episode.number, entry.days_until) == (2, 0)


def test_season_starting_today_appears_once(user, show):
    shows.set_following(user, show, True)
    season_starts(show, 3, 0)

    assert describe(dashboard.upcoming(user, "de-DE")) == [("Dark", 3, None, day(0))]


def test_finished_seasons_and_specials_are_not_upcoming(user, show):
    shows.set_following(user, show, True)
    Episode.objects.filter(season__show=show, season__number=0).update(air_date=day(5))

    assert dashboard.upcoming(user, "de-DE") == []


def test_only_followed_shows(user, show):
    other_user = User.objects.create_user(username="eve")
    shows.set_following(other_user, show, True)
    season_starts(show, 3, 5)

    assert dashboard.upcoming(user, "de-DE") == []


def test_entries_are_sorted_by_date(user, show):
    later = another_show(1, "Later")
    soon = another_show(2, "Soon")
    for followed in (show, later, soon):
        shows.set_following(user, followed, True)
    season_starts(show, 3, -10)  # next episode in 4 days
    season_starts(later, 2, 60)
    season_starts(soon, 3, 1)

    assert describe(dashboard.upcoming(user, "de-DE")) == [
        ("Soon", 3, None, day(1)),
        ("Dark", 3, 3, day(4)),
        ("Later", 2, None, day(60)),
    ]


def test_sources_include_streaming_providers(user, show):
    shows.set_following(user, show, True)
    show.networks = ["ZDF"]
    show.save()
    season_starts(show, 3, 5)

    [entry] = dashboard.upcoming(user, "de-DE")

    # Netflix from the providers; "Netflix Standard with Ads" is a variant of it
    assert entry.sources == ["ZDF", "Netflix"]


# --- Page ---------------------------------------------------------------------------------------


def test_page_groups_by_month(auth_client, user, show):
    later = another_show(1, "Later")
    for followed in (show, later):
        shows.set_following(user, followed, True)
    season_starts(show, 3, -10)
    season_starts(later, 2, 70)

    content = auth_client.get(reverse("core:upcoming")).content.decode()

    for when in (day(4), day(70)):
        assert formats.date_format(when, "F Y") in content
    assert "S3 E3" in content
    assert "Adam und Eva" in content
    assert "Staffel 2" in content
    assert "Alle aktualisieren" in content
    assert reverse("core:upcoming_refresh") in content


def test_page_without_followed_shows(auth_client):
    content = auth_client.get(reverse("core:upcoming")).content.decode()

    assert "Folge Serien, um ihre neuen Staffeln hier zu sehen." in content
    assert "Alle aktualisieren" not in content


def test_page_without_dates(auth_client, user, show):
    shows.set_following(user, show, True)

    content = auth_client.get(reverse("core:upcoming")).content.decode()

    assert "Noch keine Termine bekannt." in content


def test_navigation_marks_the_page(auth_client):
    content = auth_client.get(reverse("core:upcoming")).content.decode()

    assert f'href="{reverse("core:upcoming")}" aria-current="page"' in content


def test_dashboard_links_to_upcoming(auth_client, user, show):
    shows.set_following(user, show, True)
    season_starts(show, 3, 5)

    content = auth_client.get(reverse("core:dashboard")).content.decode()

    assert "Alle Termine" in content
