"""'Mark earlier episodes too?' after marking an episode or season on the detail page."""

from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone

from catalog import services, shows
from catalog.models import Episode, WatchedEpisode
from conftest import dark_seasons, load_tmdb_fixture

HTMX = {"HX-Request": "true"}

# "Dark": season 1 has 10 episodes, seasons 2 and 3 have 8 each, plus specials


def episode(show, season, number):
    return Episode.objects.select_related("season").get(
        season__show=show, season__number=season, number=number
    )


def watched(user, show):
    """{(season, episode): watched date} of the user's marks for `show`."""
    rows = WatchedEpisode.objects.filter(user=user, episode__season__show=show).values_list(
        "episode__season__number", "episode__number", "watched_at"
    )
    return {(season, number): watched_at for season, number, watched_at in rows}


def mark(client, show, season, number, **headers):
    url = reverse("catalog:episode_watched", args=[show.tmdb_id, season, number])
    return client.post(url, {"action": "mark"}, headers=headers)


def answer(client, show, season, number="", scope="all", **headers):
    url = reverse("catalog:watched_earlier", args=[show.tmdb_id])
    data = {"season": season, "episode": number, "scope": scope}
    return client.post(url, data, headers=headers)


# --- Rule ------------------------------------------------------------------------------------


def test_unwatched_before_an_episode(user, show):
    shows.mark_episode(user, episode(show, 1, 2))

    earlier = shows.unwatched_before(user, episode(show, 2, 3).season, episode(show, 2, 3))

    assert [e.code for e in earlier] == [
        "S1 E1",
        *(f"S1 E{n}" for n in range(3, 11)),
        "S2 E1",
        "S2 E2",
    ]


def test_unwatched_before_a_season(user, show):
    season = episode(show, 2, 1).season

    assert len(shows.unwatched_before(user, season)) == 10


def test_specials_and_unaired_episodes_are_left_out(user, show):
    Episode.objects.filter(season__show=show, season__number=1, number=5).update(
        air_date=timezone.localdate() + timedelta(days=3)
    )
    specials = show.seasons.get(number=0)

    earlier = shows.unwatched_before(user, episode(show, 2, 1).season, episode(show, 2, 1))

    assert "S1 E5" not in [e.code for e in earlier]
    assert all(e.season.number == 1 for e in earlier)
    assert shows.unwatched_before(user, specials) == []


def test_other_shows_are_left_out(user, show):
    data = {**load_tmdb_fixture("tv_70523"), "id": 1, "original_name": "Other"}
    other = services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title

    earlier = shows.unwatched_before(user, episode(other, 1, 3).season, episode(other, 1, 3))

    assert {e.season.show_id for e in earlier} == {other.pk}


# --- The question ------------------------------------------------------------------------------


def test_question_after_marking_an_episode_with_gaps(auth_client, show):
    content = mark(auth_client, show, 2, 3, **HTMX).content.decode()

    assert '<div id="toast" hx-swap-oob="innerHTML">' in content
    assert "S2 E3 gesehen. Davor sind noch 12 Folgen offen." in content
    assert "Nur Staffel 2 (2)" in content
    assert "Alle (12)" in content
    assert "Nein" in content
    assert "setTimeout" not in content  # stays until answered


def test_one_button_when_only_one_season_has_gaps(auth_client, show):
    content = mark(auth_client, show, 1, 3, **HTMX).content.decode()

    assert "S1 E3 gesehen. Davor sind noch 2 Folgen offen." in content
    assert "Ja, abhaken" in content
    assert "Nur Staffel" not in content


def test_one_button_when_only_older_seasons_have_gaps(auth_client, show):
    content = mark(auth_client, show, 2, 1, **HTMX).content.decode()

    assert "Davor sind noch 10 Folgen offen." in content
    assert "Ja, abhaken" in content
    assert "Nur Staffel" not in content


def test_no_question_without_gaps_clears_an_old_one(auth_client, show):
    content = mark(auth_client, show, 1, 1, **HTMX).content.decode()

    assert '<div id="toast" hx-swap-oob="innerHTML"></div>' in content
    assert "offen" not in content


def test_unmarking_clears_the_question(auth_client, user, show):
    shows.mark_episode(user, episode(show, 2, 3))
    url = reverse("catalog:episode_watched", args=[show.tmdb_id, 2, 3])

    content = auth_client.post(url, {"action": "unmark"}, headers=HTMX).content.decode()

    assert '<div id="toast" hx-swap-oob="innerHTML"></div>' in content


def test_question_after_marking_a_season(auth_client, show):
    url = reverse("catalog:season_watched", args=[show.tmdb_id, 3])

    content = auth_client.post(url, {"action": "mark"}, headers=HTMX).content.decode()

    assert "Staffel 3 gesehen. Davor sind noch 18 Folgen offen." in content
    assert "Ja, abhaken" in content


def test_question_without_javascript_appears_once_after_the_redirect(auth_client, show):
    response = mark(auth_client, show, 2, 3)
    page = auth_client.get(response.url).content.decode()

    assert "S2 E3 gesehen. Davor sind noch 12 Folgen offen." in page
    assert "offen." not in auth_client.get(response.url).content.decode()


# --- The answer ------------------------------------------------------------------------------


def test_all_earlier_episodes_are_marked_with_unknown_date(auth_client, user, show):
    shows.mark_episode(user, episode(show, 1, 4), date(2024, 3, 1))
    shows.mark_episode(user, episode(show, 2, 3))

    content = answer(auth_client, show, 2, 3, **HTMX).content.decode()

    marks = watched(user, show)
    assert len(marks) == 13
    assert marks[(1, 4)] == date(2024, 3, 1)  # already watched: keeps its date
    assert marks[(1, 1)] is None
    assert marks[(2, 2)] is None
    # Changed seasons and the progress line are replaced by their ids
    for part in ("season-1-toggle", "season-1-episodes", "season-2-info", "show-progress"):
        assert f'id="{part}"' in content
    assert 'id="season-3-toggle"' not in content
    assert "11 Folgen gesehen." in content  # S1 E4 was watched already
    assert 'name="undo"' in content
    assert "setTimeout" in content  # the undo message disappears


def test_only_the_same_season(auth_client, user, show):
    shows.mark_episode(user, episode(show, 2, 3))

    answer(auth_client, show, 2, 3, scope="season", **HTMX)

    assert set(watched(user, show)) == {(2, 1), (2, 2), (2, 3)}


def test_earlier_seasons_after_a_season(auth_client, user, show):
    shows.mark_season(user, show.seasons.get(number=3))

    answer(auth_client, show, 3, **HTMX)

    assert len(watched(user, show)) == 26


def test_undo_unmarks_only_the_added_episodes(auth_client, user, show):
    shows.mark_episode(user, episode(show, 2, 3))
    content = answer(auth_client, show, 2, 3, **HTMX).content.decode()
    undo = content.split('name="undo" value="')[1].split('"')[0]

    url = reverse("catalog:watched_earlier", args=[show.tmdb_id])
    content = auth_client.post(url, {"undo": undo}, headers=HTMX).content.decode()

    assert set(watched(user, show)) == {(2, 3)}
    assert '<div id="toast" hx-swap-oob="innerHTML"></div>' in content


def test_undo_ignores_episodes_of_other_shows(auth_client, user, show):
    data = {**load_tmdb_fixture("tv_70523"), "id": 1, "original_name": "Other"}
    other = services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title
    foreign = episode(other, 1, 1)
    shows.mark_episode(user, foreign)

    url = reverse("catalog:watched_earlier", args=[show.tmdb_id])
    auth_client.post(url, {"undo": str(foreign.pk)}, headers=HTMX)

    assert WatchedEpisode.objects.filter(user=user, episode=foreign).exists()


def test_answer_without_javascript_redirects_with_a_message(auth_client, user, show):
    shows.mark_episode(user, episode(show, 1, 3))

    response = answer(auth_client, show, 1, 3)
    page = auth_client.get(response.url).content.decode()

    assert response.status_code == 302
    assert "2 Folgen gesehen." in page


def test_invalid_answers(auth_client, show):
    assert answer(auth_client, show, "x", **HTMX).status_code == 400
    assert answer(auth_client, show, 2, "x", **HTMX).status_code == 400
    assert answer(auth_client, show, 9, **HTMX).status_code == 404
    url = reverse("catalog:watched_earlier", args=[show.tmdb_id])
    assert auth_client.get(url).status_code == 405
