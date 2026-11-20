"""Daily TMDB sync (`manage.py sync_tmdb`) and "Refresh all"."""

from datetime import timedelta
from io import StringIO

import httpx
import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog import services, shows, sync, tmdb
from catalog.models import Episode, TitleTranslation
from conftest import dark_seasons, load_tmdb_fixture


def details_requests(fake, tmdb_id=70523):
    return [
        r
        for r in fake.requests
        if r.url.path == f"/3/tv/{tmdb_id}"
        and r.url.params["append_to_response"] == tmdb.DETAILS_APPENDED
    ]


def make_outdated(show, hours=7):
    TitleTranslation.objects.filter(title=show).update(
        fetched_at=timezone.now() - timedelta(hours=hours)
    )


def returning_show(fake_tmdb, tmdb_id=1, name="Running"):
    """A copy of "Dark" that is still running, registered on the fake TMDB and stored."""
    data = load_tmdb_fixture("tv_70523")
    data.update(id=tmdb_id, original_name=name, status="Returning Series")
    fake_tmdb.add_show(data)
    return services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title


# --- What is synced ----------------------------------------------------------------------------


def test_followed_and_watched_shows_are_synced_in_the_users_languages(user, other_user, show):
    other_user.tmdb_language = "en-US"
    other_user.save()
    shows.set_following(user, show, True)
    first = Episode.objects.get(season__show=show, season__number=1, number=1)
    shows.mark_episode(other_user, first)
    shows.set_following(other_user, show, False)  # still "watching"

    assert sync.shows_to_sync() == {show: {"de-DE", "en-US"}}


def test_unfollowed_shows_that_nobody_watches_are_not_synced(user, show):
    shows.set_following(user, show, True)
    shows.set_following(user, show, False)

    assert sync.shows_to_sync() == {}


# --- sync_shows --------------------------------------------------------------------------------


def test_outdated_shows_are_reloaded(user, show, fake_tmdb):
    fake_tmdb.add_show()
    shows.set_following(user, show, True)
    make_outdated(show)

    result = sync.sync_shows()

    assert result.updated == ["Dark (70523)"]
    assert len(details_requests(fake_tmdb)) == 1
    assert TitleTranslation.objects.get(title=show).fetched_at > timezone.now() - timedelta(1)


def test_new_seasons_and_dates_arrive(user, show, fake_tmdb):
    """The point of the sync: changes on TMDB show up without opening the show."""
    new_date = timezone.localdate() + timedelta(days=20)

    def seasons(language):
        data = dark_seasons(language)
        data[3]["episodes"][0]["air_date"] = new_date.isoformat()
        return data

    fake_tmdb.add_show(seasons=seasons)
    shows.set_following(user, show, True)
    make_outdated(show)

    sync.sync_shows()

    assert Episode.objects.get(season__show=show, season__number=3, number=1).air_date == new_date


def test_recently_loaded_shows_are_skipped(user, show, fake_tmdb):
    shows.set_following(user, show, True)

    result = sync.sync_shows()

    assert result.skipped == ["Dark (70523)"]
    assert fake_tmdb.requests == []


def test_force_reloads_fresh_shows(user, show, fake_tmdb):
    fake_tmdb.add_show()
    shows.set_following(user, show, True)

    result = sync.sync_shows(max_age=None)

    assert result.updated == ["Dark (70523)"]


def test_missing_language_is_loaded(user, show, fake_tmdb):
    """A user with another language follows the show: it isn't fresh for them yet."""
    fake_tmdb.add_show()
    user.tmdb_language = "en-US"
    user.save()
    shows.set_following(user, show, True)

    sync.sync_shows()

    assert details_requests(fake_tmdb)[0].url.params["language"] == "en-US"
    assert TitleTranslation.objects.filter(title=show, language="en-US").exists()


def test_new_region_is_loaded(user, show, fake_tmdb):
    fake_tmdb.add_show()
    shows.set_following(user, show, True)
    User.objects.create_user(username="carla", region="AT")

    result = sync.sync_shows()

    assert result.updated == ["Dark (70523)"]
    show.refresh_from_db()
    assert "AT" in show.watch_providers


def test_one_failure_does_not_stop_the_sync(user, show, fake_tmdb):
    other = returning_show(fake_tmdb)
    fake_tmdb.add("/3/tv/70523", json=lambda request: httpx.Response(500))
    for followed in (show, other):
        shows.set_following(user, followed, True)
        make_outdated(followed)

    result = sync.sync_shows()

    assert result.failed == ["Dark (70523)"]
    assert result.updated == ["Running (1)"]


def test_show_removed_from_tmdb_keeps_its_data(user, show, fake_tmdb):
    fake_tmdb.add("/3/tv/70523", status=404, json={})
    shows.set_following(user, show, True)
    make_outdated(show)

    result = sync.sync_shows()

    assert result.failed == ["Dark (70523)"]
    assert show.seasons.count() > 0


# --- Command ------------------------------------------------------------------------------------


def test_command_prints_a_summary(user, show, fake_tmdb):
    fake_tmdb.add_show()
    shows.set_following(user, show, True)
    make_outdated(show)
    out = StringIO()

    call_command("sync_tmdb", stdout=out)

    assert "TMDB sync: 1 updated, 0 skipped (loaded recently), 0 failed." in out.getvalue()


def test_command_force_and_verbose(user, show, fake_tmdb):
    fake_tmdb.add_show()
    shows.set_following(user, show, True)
    out = StringIO()

    call_command("sync_tmdb", "--force", verbosity=2, stdout=out)

    assert "Dark (70523): updated" in out.getvalue()


def test_command_reports_failures(user, show, fake_tmdb):
    fake_tmdb.add("/3/tv/70523", json=lambda request: httpx.Response(500))
    shows.set_following(user, show, True)
    make_outdated(show)
    out, err = StringIO(), StringIO()

    call_command("sync_tmdb", stdout=out, stderr=err)

    assert "Failed: Dark (70523)" in err.getvalue()
    assert "1 failed" in out.getvalue()


def test_command_without_token_fails(user, show, settings):
    shows.set_following(user, show, True)
    settings.TMDB_API_TOKEN = ""

    with pytest.raises(CommandError, match="TMDB_API_TOKEN"):
        call_command("sync_tmdb", stdout=StringIO())


def test_crontab_runs_the_sync():
    from django.conf import settings

    crontab = (settings.BASE_DIR / "docker" / "crontab").read_text()

    assert "python manage.py sync_tmdb" in crontab


# --- "Refresh all" ------------------------------------------------------------------------------


def test_refresh_followed_skips_ended_shows(user, show, fake_tmdb):
    running = returning_show(fake_tmdb)
    for followed in (show, running):  # "Dark" has ended
        shows.set_following(user, followed, True)

    result = sync.refresh_followed(user)

    assert result.updated == ["Running (1)"]
    assert details_requests(fake_tmdb, 70523) == []


def test_refresh_all_button(auth_client, user, fake_tmdb):
    shows.set_following(user, returning_show(fake_tmdb), True)

    response = auth_client.post(reverse("core:upcoming_refresh"), follow=True)

    assert response.redirect_chain[-1][0] == reverse("core:upcoming")
    assert "1 Serie aktualisiert." in response.content.decode()
    assert len(details_requests(fake_tmdb, 1)) == 1


def test_refresh_all_is_throttled(auth_client, user, fake_tmdb):
    shows.set_following(user, returning_show(fake_tmdb), True)
    auth_client.post(reverse("core:upcoming_refresh"))

    response = auth_client.post(reverse("core:upcoming_refresh"), follow=True)

    assert "Bitte warte ein paar Minuten." in response.content.decode()
    assert len(details_requests(fake_tmdb, 1)) == 1


def test_refresh_all_reports_failures(auth_client, user, fake_tmdb):
    shows.set_following(user, returning_show(fake_tmdb, 1, "A"), True)
    shows.set_following(user, returning_show(fake_tmdb, 2, "B"), True)
    fake_tmdb.add("/3/tv/2", json=lambda request: httpx.Response(500))

    response = auth_client.post(reverse("core:upcoming_refresh"), follow=True)

    assert "1 von 2 Serien aktualisiert." in response.content.decode()


def test_refresh_all_when_tmdb_is_down(auth_client, user, fake_tmdb):
    shows.set_following(user, returning_show(fake_tmdb), True)
    fake_tmdb.add("/3/tv/1", json=lambda request: httpx.Response(500))

    response = auth_client.post(reverse("core:upcoming_refresh"), follow=True)

    assert "TMDB ist gerade nicht erreichbar." in response.content.decode()


def test_refresh_all_requires_post(auth_client):
    assert auth_client.get(reverse("core:upcoming_refresh")).status_code == 405


# --- "Refresh now" on the detail page -----------------------------------------------------------


def test_refresh_now_reloads_the_title(auth_client, user, show, fake_tmdb):
    fake_tmdb.add_show()

    response = auth_client.post(reverse("catalog:title_refresh", args=["tv", 70523]), follow=True)

    assert response.redirect_chain[-1][0] == show.get_absolute_url()
    assert "Von TMDB aktualisiert." in response.content.decode()
    assert len(details_requests(fake_tmdb)) == 1


def test_refresh_now_when_tmdb_is_down(auth_client, show, fake_tmdb):
    fake_tmdb.add("/3/tv/70523", json=lambda request: httpx.Response(500))

    response = auth_client.post(reverse("catalog:title_refresh", args=["tv", 70523]), follow=True)

    assert "TMDB ist gerade nicht erreichbar." in response.content.decode()


def test_refresh_now_is_throttled(auth_client, movie, fake_tmdb):
    fake_tmdb.add("/3/movie/155", json=load_tmdb_fixture("movie_155"))
    url = reverse("catalog:title_refresh", args=["movie", 155])
    for _ in range(10):
        auth_client.post(url)

    response = auth_client.post(url, follow=True)

    assert "Zu viele Aktualisierungen" in response.content.decode()
    assert len(fake_tmdb.requests) == 10


def test_refresh_now_unknown_title_is_404(auth_client, fake_tmdb):
    fake_tmdb.add("/3/movie/1", status=404, json={})

    assert auth_client.post(reverse("catalog:title_refresh", args=["movie", 1])).status_code == 404


def test_detail_page_has_refresh_button(auth_client, movie):
    content = auth_client.get(movie.get_absolute_url()).content.decode()

    assert reverse("catalog:title_refresh", args=["movie", 155]) in content
    assert "Jetzt aktualisieren" in content
    assert "Daten von TMDB und JustWatch, Stand" in content
