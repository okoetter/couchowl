"""Shows: loading seasons from TMDB, episode tracking rules, detail page, following."""

from datetime import date, timedelta

import httpx
import pytest
from django.urls import reverse
from django.utils import timezone

from catalog import services, shows, tmdb
from catalog.models import Episode, EpisodeTranslation, Season, UserSeries, WatchedEpisode
from conftest import dark_seasons, load_tmdb_fixture

HTMX = {"HX-Request": "true"}


def episode(show, season, number):
    return Episode.objects.select_related("season").get(
        season__show=show, season__number=season, number=number
    )


def season_requests(fake):
    return [
        r for r in fake.requests if r.url.params.get("append_to_response", "").startswith("season/")
    ]


# --- Loading seasons from TMDB ----------------------------------------------------------------


def test_fallback_languages():
    assert services.fallback_languages("de-AT") == ["de-AT", "de", "en-US"]
    assert services.fallback_languages("de-DE") == ["de-DE", "en-US"]
    assert services.fallback_languages("en-US") == ["en-US"]
    assert services.fallback_languages("en-GB") == ["en-GB", "en"]
    assert services.fallback_languages("fr") == ["fr", "en-US"]


@pytest.mark.django_db
def test_get_title_stores_seasons_and_episodes(fake_tmdb):
    fake_tmdb.add_show()

    show = services.get_title("tv", 70523, "de-DE").title

    assert list(show.seasons.values_list("number", flat=True)) == [0, 1, 2, 3]
    assert Episode.objects.filter(season__show=show).count() == 5 + 10 + 8 + 8
    first = episode(show, 1, 1)
    assert first.air_date == date(2017, 12, 1)
    assert first.runtime == 52
    assert first.tmdb_id == 1279454
    assert first.translations.get(language="de-DE").name == "Geheimnisse"
    # All seasons in one request (append_to_response), German texts are complete
    assert len(season_requests(fake_tmdb)) == 1
    appended = season_requests(fake_tmdb)[0].url.params["append_to_response"]
    assert appended == "season/0,season/1,season/2,season/3"


@pytest.mark.django_db
def test_english_season_placeholder_shows_the_translated_default_name(fake_tmdb, user):
    # Without a German name TMDB sends "Season 3" (in English) for de-DE
    def seasons(language):
        data = dark_seasons(language)
        data[3]["name"] = "Season 3"
        data[2]["name"] = "Season 2: Die Reise"  # a real name that starts like one
        return data

    fake_tmdb.add_show(seasons=seasons)
    show = services.get_title("tv", 70523, "de-DE").title

    assert show.seasons.get(number=3).translations.get().name == ""
    names = {s.number: s.name for s in shows.seasons_overview(user, show, "de-DE")}
    assert names[3] == "Staffel 3"
    assert names[2] == "Season 2: Die Reise"


@pytest.mark.django_db
def test_missing_episode_texts_come_from_the_next_language(fake_tmdb):
    # Like the real TMDB: "de-AT" only has placeholders ("Episode 1", no description)
    fake_tmdb.add_show()

    show = services.get_title("tv", 70523, "de-AT").title

    text = episode(show, 1, 2).translations.get(language="de-AT")
    assert text.name == "Lügen"
    assert text.overview.startswith("Die Polizei ist nach einer düsteren Entdeckung")
    assert [r.url.params["language"] for r in season_requests(fake_tmdb)] == ["de-AT", "de"]


@pytest.mark.django_db
def test_further_languages_are_only_asked_for_seasons_with_missing_texts(fake_tmdb):
    def seasons(language):
        data = dark_seasons(language)
        if language == "de-DE":
            data[2]["episodes"][0]["overview"] = ""
        return data

    fake_tmdb.add_show(seasons=seasons)

    show = services.get_title("tv", 70523, "de-DE").title

    english = season_requests(fake_tmdb)[1]
    assert english.url.params["language"] == "en-US"
    assert english.url.params["append_to_response"] == "season/2"
    text = episode(show, 2, 1).translations.get(language="de-DE")
    assert text.name == "Beginnings and Endings"  # name and description from the same language
    assert episode(show, 2, 2).translations.get(language="de-DE").name == "Dunkle Materie"


@pytest.mark.django_db
def test_long_shows_load_their_seasons_in_batches_of_20(fake_tmdb):
    details = load_tmdb_fixture("tv_70523")
    details["seasons"] = [{"season_number": n} for n in range(1, 26)]
    template = dark_seasons("de-DE")[1]
    many = {n: {**template, "season_number": n} for n in range(1, 26)}
    fake_tmdb.add_show(details, seasons=lambda language: many)

    show = services.get_title("tv", 70523, "de-DE").title

    batches = [r.url.params["append_to_response"].count("season/") for r in fake_tmdb.requests[1:]]
    assert batches == [20, 5]
    assert show.seasons.count() == 25
    assert Episode.objects.filter(season__show=show).count() == 25 * 10


@pytest.mark.django_db
def test_reloading_updates_episodes_and_removes_vanished_ones(show, user):
    shows.mark_episode(user, episode(show, 1, 10))
    seasons = dark_seasons("de-DE")
    seasons[1]["episodes"] = seasons[1]["episodes"][:9]  # episode 10 is gone
    seasons[1]["episodes"][0]["air_date"] = "2017-11-30"
    del seasons[3]

    services.save_title("tv", load_tmdb_fixture("tv_70523"), "de-DE", seasons=seasons)

    assert list(show.seasons.values_list("number", flat=True)) == [0, 1, 2]
    assert show.seasons.get(number=1).episodes.count() == 9
    assert episode(show, 1, 1).air_date == date(2017, 11, 30)
    assert not WatchedEpisode.objects.exists()


@pytest.mark.django_db
def test_a_second_language_adds_texts_but_no_episodes(show):
    episode_ids = set(Episode.objects.values_list("pk", flat=True))

    data = load_tmdb_fixture("tv_70523")
    services.save_title("tv", data, "en-US", seasons=dark_seasons("en-US"))

    assert set(Episode.objects.values_list("pk", flat=True)) == episode_ids
    first = episode(show, 1, 1)
    assert set(first.translations.values_list("language", "name")) == {
        ("de-DE", "Geheimnisse"),
        ("en-US", "Secrets"),
    }


def failing_season_requests(request):
    """Details work, season requests fail."""
    if request.url.params["append_to_response"] == tmdb.DETAILS_APPENDED:
        return load_tmdb_fixture("tv_70523")
    return httpx.Response(503)


@pytest.mark.django_db
def test_season_errors_fall_back_to_stored_data(fake_tmdb, show):
    from catalog.models import TitleTranslation

    TitleTranslation.objects.update(fetched_at=timezone.now() - timedelta(days=3))
    fake_tmdb.add("/3/tv/70523", json=failing_season_requests)

    result = services.get_title("tv", 70523, "de-DE")

    assert result.title == show
    assert Episode.objects.filter(season__show=show).count() == 31


@pytest.mark.django_db
def test_season_errors_are_raised_without_stored_data(fake_tmdb):
    fake_tmdb.add("/3/tv/70523", json=failing_season_requests)

    with pytest.raises(tmdb.TMDBError):
        services.get_title("tv", 70523, "de-DE")


# --- Rules: progress and next episode ---------------------------------------------------------


def test_progress_ignores_specials(user, show):
    progress = shows.progress(user, [show])[show.pk]

    assert (progress.watched, progress.aired) == (0, 26)
    assert progress.next_episode.code == "S1 E1"
    assert not progress.started
    assert not progress.complete


def test_next_episode_is_the_first_unwatched_aired_one(user, show):
    for number in (1, 2, 4):
        shows.mark_episode(user, episode(show, 1, number))
    shows.mark_episode(user, episode(show, 0, 1))  # specials don't count

    progress = shows.progress(user, [show])[show.pk]

    assert progress.next_episode == episode(show, 1, 3)
    assert progress.watched == 3
    assert progress.started


def test_episodes_that_have_not_aired_cannot_be_marked(user, show):
    upcoming = episode(show, 3, 8)
    upcoming.air_date = timezone.localdate() + timedelta(days=1)
    upcoming.save()

    assert not shows.mark_episode(user, upcoming)
    assert not WatchedEpisode.objects.exists()
    assert shows.progress(user, [show])[show.pk].aired == 25


def test_show_is_complete_until_a_new_episode_airs(user, show):
    new = episode(show, 3, 8)
    new.air_date = None
    new.save()
    for season in show.seasons.all():
        shows.mark_season(user, season)

    assert shows.progress(user, [show])[show.pk].complete
    assert shows.progress(user, [show])[show.pk].next_episode is None

    new.air_date = timezone.localdate()
    new.save()

    progress = shows.progress(user, [show])[show.pk]
    assert not progress.complete
    assert progress.next_episode == new


def test_progress_is_per_user(user, other_user, show):
    shows.mark_episode(other_user, episode(show, 1, 1))

    assert shows.progress(user, [show])[show.pk].watched == 0


def test_watch_next_marks_today(user, show):
    shows.mark_episode(user, episode(show, 1, 1), date(2020, 1, 1))

    marked = shows.watch_next(user, show)

    assert marked == episode(show, 1, 2)
    assert WatchedEpisode.objects.get(episode=marked).watched_at == timezone.localdate()


def test_watch_next_does_nothing_when_everything_is_watched(user, show):
    for season in show.seasons.all():
        shows.mark_season(user, season)

    assert shows.watch_next(user, show) is None


def test_first_watched_episode_starts_watching(user, show):
    assert not UserSeries.objects.exists()

    shows.mark_episode(user, episode(show, 1, 1))

    assert UserSeries.objects.get(user=user, title=show).status == "watching"


def test_first_watched_episode_follows_the_show(user, show):
    shows.mark_season(user, show.seasons.get(number=1))

    series = UserSeries.objects.get(user=user, title=show)
    assert series.following
    assert series.followed_at is not None


def test_first_watched_episode_keeps_an_earlier_follow_date(user, show):
    shows.set_following(user, show, True)
    followed_at = UserSeries.objects.get(user=user, title=show).followed_at

    shows.mark_episode(user, episode(show, 1, 1))

    assert UserSeries.objects.get(user=user, title=show).followed_at == followed_at


def test_watching_more_episodes_respects_an_unfollow(user, show):
    shows.mark_episode(user, episode(show, 1, 1))
    shows.set_following(user, show, False)

    shows.mark_episode(user, episode(show, 1, 2))
    shows.watch_next(user, show)

    assert not shows.is_following(user, show)


def test_marking_a_season_keeps_existing_dates(user, show):
    shows.mark_episode(user, episode(show, 1, 1), date(2020, 1, 1))

    shows.mark_season(user, show.seasons.get(number=1))

    dates = dict(
        WatchedEpisode.objects.filter(user=user).values_list("episode__number", "watched_at")
    )
    assert dates[1] == date(2020, 1, 1)
    assert dates[2] == timezone.localdate()
    assert len(dates) == 10


def test_season_date_applies_to_all_its_episodes(user, show):
    season = show.seasons.get(number=1)
    shows.mark_episode(user, episode(show, 1, 1), date(2020, 1, 1))

    shows.mark_season(user, season, unknown_date=True, keep_existing=False)

    assert set(WatchedEpisode.objects.values_list("watched_at", flat=True)) == {None}
    assert WatchedEpisode.objects.count() == 10


def test_unmark_season(user, show):
    shows.mark_season(user, show.seasons.get(number=1))
    shows.mark_episode(user, episode(show, 2, 1))

    shows.unmark_season(user, show.seasons.get(number=1))

    assert list(WatchedEpisode.objects.values_list("episode__season__number", flat=True)) == [2]


def test_unmark_show_keeps_following_and_other_users(user, other_user, show):
    for season in show.seasons.all():  # specials included
        shows.mark_season(user, season)
        shows.mark_season(other_user, season)
    status = UserSeries.objects.get(user=user).status

    shows.unmark_show(user, show)

    assert not WatchedEpisode.objects.filter(user=user).exists()
    assert WatchedEpisode.objects.filter(user=other_user).exists()
    assert shows.is_following(user, show)
    assert UserSeries.objects.get(user=user).status == status


def test_follow_and_unfollow(user, show):
    shows.set_following(user, show, True)
    assert shows.is_following(user, show)
    assert UserSeries.objects.get().followed_at is not None

    shows.set_following(user, show, False)
    assert not shows.is_following(user, show)
    assert not shows.followed_shows(user).exists()


# --- Detail page ------------------------------------------------------------------------------


def test_detail_page_shows_seasons_with_the_next_season_open(auth_client, user, show):
    shows.mark_season(user, show.seasons.get(number=1))
    shows.mark_episode(user, episode(show, 2, 1), date(2024, 3, 15))

    content = auth_client.get(show.get_absolute_url()).content.decode()

    # Specials last
    names = ["Staffel 1", "Staffel 2", "Staffel 3", "Extras"]
    positions = [content.index(f"<strong>{name}</strong>") for name in names]
    assert positions == sorted(positions)
    assert "11 von 26 Folgen gesehen" in content
    assert "<strong>S2 E2</strong> Dunkle Materie" in content
    # Season 2 is open with its episodes; the others load theirs when opened
    assert 'id="episode-2-2"' in content
    assert 'id="episode-1-1"' not in content
    assert reverse("catalog:season_episodes", args=[70523, 1]) in content
    assert "✓ Gesehen" in content  # season 1
    assert "1/8 gesehen" in content
    assert "zuletzt am 15.03.2024" in content


def test_season_from_the_url_is_open(auth_client, show):
    content = auth_client.get(show.get_absolute_url(), {"season": "3"}).content.decode()

    assert 'id="episode-3-1"' in content
    assert 'id="episode-1-1"' not in content


def test_episode_descriptions_are_hidden_until_opened(auth_client, show):
    content = auth_client.get(show.get_absolute_url()).content.decode()

    assert '<summary><span class="episode-number">1</span> Geheimnisse</summary>' in content


def test_lazy_loaded_season(auth_client, show):
    url = reverse("catalog:season_episodes", args=[70523, 3])

    response = auth_client.get(url, headers=HTMX)

    content = response.content.decode()
    assert "<html" not in content
    assert 'id="episode-3-8"' in content
    assert "hx-get" not in content.split('id="season-3-episodes"')[1].split(">")[0]
    # Without JavaScript: the detail page with this season open
    response = auth_client.get(url)
    assert response["Location"] == "/tv/70523/?season=3#season-3"


def test_unknown_season_is_404(auth_client, show):
    url = reverse("catalog:season_episodes", args=[70523, 9])

    assert auth_client.get(url, headers=HTMX).status_code == 404


def test_upcoming_episode_has_no_button(auth_client, show):
    upcoming = episode(show, 1, 10)
    upcoming.air_date = date(2099, 1, 1)
    upcoming.save()

    content = auth_client.get(show.get_absolute_url()).content.decode()

    row = content.split('id="episode-1-10"')[1].split("</li>")[0]
    assert "<button" not in row
    assert "Erscheint am 01.01.2099" in row


# --- Marking episodes and seasons (htmx) ------------------------------------------------------


def episode_url(season, number):
    return reverse("catalog:episode_watched", args=[70523, season, number])


def season_url(season):
    return reverse("catalog:season_watched", args=[70523, season])


def test_mark_episode_updates_the_page_in_place(auth_client, user, show):
    response = auth_client.post(episode_url(1, 1), {"action": "mark"}, headers=HTMX)

    content = response.content.decode()
    watched = WatchedEpisode.objects.get(user=user)
    assert watched.episode == episode(show, 1, 1)
    assert watched.watched_at == timezone.localdate()
    assert content.lstrip().startswith('<li id="episode-1-1"')
    assert 'id="season-1-toggle"' in content
    assert 'id="season-1-info" class="season-info" hx-swap-oob="true"' in content
    assert 'id="show-progress" class="show-progress" hx-swap-oob="true"' in content
    assert "1 von 26 Folgen gesehen" in content
    assert "<img" not in content


def test_unmark_episode(auth_client, user, show):
    shows.mark_episode(user, episode(show, 1, 1))

    auth_client.post(episode_url(1, 1), {"action": "unmark"}, headers=HTMX)

    assert not WatchedEpisode.objects.exists()


def test_change_episode_date(auth_client, user, show):
    shows.mark_episode(user, episode(show, 1, 1))

    content = auth_client.post(
        episode_url(1, 1), {"action": "date", "e1-1-watched_at": "2024-03-15"}, headers=HTMX
    ).content.decode()

    assert WatchedEpisode.objects.get().watched_at == date(2024, 3, 15)
    assert "15.03.2024" in content


def test_episode_date_in_the_future_is_rejected(auth_client, user, show):
    shows.mark_episode(user, episode(show, 1, 1), date(2020, 1, 1))
    tomorrow = timezone.localdate() + timedelta(days=1)

    content = auth_client.post(
        episode_url(1, 1), {"action": "date", "e1-1-watched_at": tomorrow}, headers=HTMX
    ).content.decode()

    assert WatchedEpisode.objects.get().watched_at == date(2020, 1, 1)
    assert "nicht in der Zukunft" in content


def test_episode_actions_without_javascript(auth_client, user, show):
    response = auth_client.post(episode_url(2, 3), {"action": "mark"})

    assert response["Location"] == "/tv/70523/?season=2#episode-2-3"
    assert WatchedEpisode.objects.count() == 1


def test_marking_an_upcoming_episode_changes_nothing(auth_client, show):
    upcoming = episode(show, 1, 10)
    upcoming.air_date = date(2099, 1, 1)
    upcoming.save()

    auth_client.post(episode_url(1, 10), {"action": "mark"}, headers=HTMX)

    assert not WatchedEpisode.objects.exists()


def test_mark_and_unmark_season(auth_client, user, show):
    content = auth_client.post(season_url(1), {"action": "mark"}, headers=HTMX).content.decode()

    assert WatchedEpisode.objects.filter(user=user).count() == 10
    assert 'id="season-1-episodes" class="season-episodes"\n               hx-swap-oob="true"' in (
        content
    )
    assert "Staffel gesehen" in content
    assert "hx-confirm" in content  # undoing a whole season asks first

    auth_client.post(season_url(1), {"action": "unmark"}, headers=HTMX)
    assert not WatchedEpisode.objects.exists()


def test_mark_whole_show_as_not_watched(auth_client, user, show):
    url = reverse("catalog:show_unwatched", args=[70523])
    assert url not in auth_client.get(show.get_absolute_url()).content.decode()
    shows.mark_season(user, show.seasons.get(number=1))
    shows.mark_episode(user, episode(show, 2, 1))

    content = auth_client.get(show.get_absolute_url()).content.decode()
    assert url in content
    assert "Alle Folgen dieser Serie als nicht gesehen markieren?" in content  # asks first

    content = auth_client.post(url, headers=HTMX).content.decode()

    assert not WatchedEpisode.objects.exists()
    assert '<section id="seasons"' in content
    assert 'id="show-progress" class="show-progress" hx-swap-oob="true"' in content
    assert "0 von 26 Folgen gesehen" in content
    assert url not in content  # nothing left to unmark
    assert 'id="toast" hx-swap-oob="innerHTML"' in content  # an open prompt disappears


def test_mark_whole_show_as_not_watched_without_javascript(auth_client, user, show):
    shows.mark_episode(user, episode(show, 1, 1))

    response = auth_client.post(reverse("catalog:show_unwatched", args=[70523]))

    assert response.url == show.get_absolute_url()
    assert not WatchedEpisode.objects.exists()


def test_season_date(auth_client, user, show):
    shows.mark_season(user, show.seasons.get(number=1))

    auth_client.post(season_url(1), {"action": "date", "s1-unknown": "on"}, headers=HTMX)

    assert set(WatchedEpisode.objects.values_list("watched_at", flat=True)) == {None}


def test_invalid_action_is_rejected(auth_client, show):
    assert auth_client.post(season_url(1), {"action": "x"}).status_code == 400
    assert auth_client.post(episode_url(1, 1), {"action": "x"}).status_code == 400


def test_actions_on_shows_that_are_not_stored_are_404(auth_client, db):
    assert auth_client.post(episode_url(1, 1), {"action": "mark"}).status_code == 404


# --- Follow -----------------------------------------------------------------------------------


def test_follow_button(auth_client, user, show):
    url = reverse("catalog:show_follow", args=[70523])
    assert "Folgen</button>" in auth_client.get(show.get_absolute_url()).content.decode()

    content = auth_client.post(url, {"following": "1"}, headers=HTMX).content.decode()
    assert "Gefolgt</button>" in content
    assert shows.is_following(user, show)

    auth_client.post(url, {}, headers=HTMX)
    assert not shows.is_following(user, show)


def test_follow_without_javascript(auth_client, show):
    response = auth_client.post(reverse("catalog:show_follow", args=[70523]), {"following": "1"})

    assert response["Location"] == show.get_absolute_url()


def test_movies_cannot_be_followed(auth_client, movie):
    response = auth_client.post(reverse("catalog:show_follow", args=[155]), {"following": "1"})

    assert response.status_code == 404


# --- Texts ------------------------------------------------------------------------------------


def test_episode_without_texts_gets_a_generic_name(user, show):
    EpisodeTranslation.objects.filter(episode=episode(show, 1, 1)).delete()

    rows = shows.season_episodes(user, Season.objects.get(show=show, number=1), "de-DE")

    assert rows[0].name == "Folge 1"


def test_watched_date_is_in_the_same_line_as_the_air_date(auth_client, user, show):
    # Marking an episode must not add a line (the row would change its height)
    shows.mark_episode(user, episode(show, 1, 1), date(2024, 3, 15))

    content = auth_client.get(show.get_absolute_url()).content.decode()

    meta = content.split('id="episode-1-1"')[1].split('<div class="episode-meta">')[1]
    meta = meta.split("<form")[0]
    assert "01.12.2017" in meta  # short dates: fits in one line on phones
    assert "15.03.2024" in meta
