"""Detail pages of movies and shows, "watched" with date, watched state in search."""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog import lists as list_rules
from catalog.models import WatchedMovie
from conftest import load_tmdb_fixture

HTMX = {"HX-Request": "true"}


def watched_url(tmdb_id=155):
    return reverse("catalog:movie_watched", args=[tmdb_id])


# --- Detail page -------------------------------------------------------------------------------


def test_movie_detail_page(auth_client, fake_tmdb):
    fake_tmdb.add("/3/movie/155", json=load_tmdb_fixture("movie_155"))

    response = auth_client.get("/movie/155/")

    content = response.content.decode()
    assert response.status_code == 200
    assert "<h1>The Dark Knight</h1>" in content
    assert "Film · 2008 · Veröffentlicht" in content
    assert "Gemeinsam mit Bezirksstaatsanwalt" in content
    assert "/posters/w342/54WAzARB0rTp5L7gvCcfZ49AgkX.jpg" in content
    assert "Als gesehen markieren" in content
    assert "Zu Liste hinzufügen" in content
    assert fake_tmdb.requests[0].url.params["language"] == "de-DE"


def test_show_detail_page_tracks_episodes_instead_of_the_show(auth_client, show):
    content = auth_client.get(show.get_absolute_url()).content.decode()

    assert "<h1>Dark</h1>" in content
    assert "Serie · 2017 · Beendet" in content
    assert 'id="watched"' not in content  # the movie's watched section
    assert "Staffeln</h2>" in content
    assert "Zu Liste hinzufügen" in content


def test_detail_page_links_to_tmdb_in_the_users_language(auth_client, movie, show):
    content = auth_client.get(movie.get_absolute_url()).content.decode()
    assert 'href="https://www.themoviedb.org/movie/155?language=de-DE"' in content
    assert "Film bei TMDB ansehen" in content

    content = auth_client.get(show.get_absolute_url()).content.decode()
    assert 'href="https://www.themoviedb.org/tv/70523?language=de-DE"' in content
    assert "Serie bei TMDB ansehen" in content


def test_tmdb_url(movie):
    assert movie.tmdb_url() == "https://www.themoviedb.org/movie/155"
    assert movie.tmdb_url("pt-BR") == "https://www.themoviedb.org/movie/155?language=pt-BR"


def test_detail_page_shows_list_membership(auth_client, user, movie):
    watchlist = user.lists.create(name="Watchlist")
    list_rules.add_to_list(watchlist, movie)

    content = auth_client.get(movie.get_absolute_url()).content.decode()

    assert f'id="list-movie-155-{watchlist.pk}"\n               checked' in content


def test_unknown_title_is_404(auth_client, fake_tmdb):
    fake_tmdb.add("/3/movie/999", json={}, status=404)

    assert auth_client.get("/movie/999/").status_code == 404


def test_detail_page_when_tmdb_is_down(auth_client, fake_tmdb):
    fake_tmdb.add("/3/movie/155", json={}, status=503)

    response = auth_client.get("/movie/155/")

    assert response.status_code == 503
    assert "TMDB ist gerade nicht erreichbar" in response.content.decode()


def test_only_movie_and_tv_urls_exist(auth_client):
    assert auth_client.get("/person/155/").status_code == 404


# --- Watched -----------------------------------------------------------------------------------


def test_mark_as_watched_stores_today(auth_client, user, movie):
    response = auth_client.post(watched_url(), {"action": "mark"}, headers=HTMX)

    watched = WatchedMovie.objects.get(user=user, title=movie)
    assert watched.watched_at == timezone.localdate()
    content = response.content.decode()
    assert "<html" not in content
    assert 'id="watched"' in content
    assert "✓ Gesehen" in content
    assert "Als nicht gesehen markieren" in content


def test_mark_without_javascript_redirects_to_detail_page(auth_client, user, movie):
    response = auth_client.post(watched_url(), {"action": "mark"})

    assert response["Location"] == movie.get_absolute_url()
    assert WatchedMovie.objects.filter(user=user, title=movie).exists()


def test_watching_again_replaces_the_date(auth_client, user, movie):
    list_rules.mark_watched(user, movie, date(2020, 1, 1))

    auth_client.post(watched_url(), {"action": "mark"}, headers=HTMX)

    assert WatchedMovie.objects.get(user=user, title=movie).watched_at == timezone.localdate()


def test_change_date(auth_client, user, movie):
    list_rules.mark_watched(user, movie)

    response = auth_client.post(
        watched_url(), {"action": "date", "watched_at": "2024-03-15"}, headers=HTMX
    )

    assert WatchedMovie.objects.get(user=user, title=movie).watched_at == date(2024, 3, 15)
    assert "am 15. März 2024" in response.content.decode()


def test_date_unknown(auth_client, user, movie):
    list_rules.mark_watched(user, movie)

    response = auth_client.post(
        watched_url(), {"action": "date", "watched_at": "2024-03-15", "unknown": "on"}, headers=HTMX
    )

    watched = WatchedMovie.objects.get(user=user, title=movie)
    assert watched.watched_at is None
    assert "Datum unbekannt" in response.content.decode()


def test_setting_a_date_also_marks_as_watched(auth_client, user, movie):
    auth_client.post(watched_url(), {"action": "date", "watched_at": "2024-03-15"}, headers=HTMX)

    assert WatchedMovie.objects.get(user=user, title=movie).watched_at == date(2024, 3, 15)


@pytest.mark.parametrize(
    ("data", "error"),
    [
        ({}, "Gib ein Datum ein"),
        ({"watched_at": "kein Datum"}, "gültiges Datum"),
        ({"watched_at": (date.today() + timedelta(days=2)).isoformat()}, "Zukunft"),
    ],
)
def test_invalid_dates_are_rejected(auth_client, user, movie, data, error):
    list_rules.mark_watched(user, movie, date(2020, 1, 1))

    response = auth_client.post(watched_url(), {"action": "date", **data}, headers=HTMX)

    content = response.content.decode()
    assert error in content
    assert 'class="watched-edit" open' in content
    assert WatchedMovie.objects.get(user=user, title=movie).watched_at == date(2020, 1, 1)


def test_unmark_removes_watched_state(auth_client, user, movie):
    list_rules.mark_watched(user, movie)

    response = auth_client.post(watched_url(), {"action": "unmark"}, headers=HTMX)

    assert not WatchedMovie.objects.exists()
    assert "Als gesehen markieren" in response.content.decode()


def test_watched_is_per_user(auth_client, user, other_user, movie):
    list_rules.mark_watched(other_user, movie)

    content = auth_client.get(movie.get_absolute_url()).content.decode()

    assert "Als gesehen markieren" in content
    auth_client.post(watched_url(), {"action": "unmark"})
    assert WatchedMovie.objects.filter(user=other_user).exists()


def test_shows_cannot_be_marked_as_watched_here(auth_client, show):
    response = auth_client.post(watched_url(show.tmdb_id), {"action": "mark"})

    assert response.status_code == 404


def test_unknown_action_is_rejected(auth_client, movie):
    assert auth_client.post(watched_url(), {"action": "explode"}).status_code == 400


def test_watched_requires_post(auth_client, movie):
    assert auth_client.get(watched_url()).status_code == 405


# --- Search ------------------------------------------------------------------------------------


def test_search_marks_watched_movies_and_links_to_details(auth_client, user, movie, fake_tmdb):
    fake_tmdb.add("/3/search/multi", json=load_tmdb_fixture("search_multi"))
    list_rules.mark_watched(user, movie)

    content = auth_client.get(reverse("catalog:search"), {"q": "dark"}).content.decode()

    assert content.count("✓ Gesehen") == 1
    assert 'href="/movie/155/"' in content
    assert 'href="/tv/70523/"' in content
    assert 'hx-get="/tv/70523/lists/"' in content


def test_search_marks_completely_watched_shows(auth_client, user, show, fake_tmdb):
    from catalog import shows

    fake_tmdb.add("/3/search/multi", json=load_tmdb_fixture("search_multi"))
    shows.mark_season(user, show.seasons.get(number=1))

    content = auth_client.get(reverse("catalog:search"), {"q": "dark"}).content.decode()
    assert "✓ Gesehen" not in content  # seasons 2 and 3 are still missing

    for season in show.seasons.all():
        shows.mark_season(user, season)

    content = auth_client.get(reverse("catalog:search"), {"q": "dark"}).content.decode()
    row = content.split('id="result-tv-70523"')[1].split("</li>")[0]
    assert "✓ Gesehen" in row
