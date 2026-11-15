import pytest
from django.urls import reverse

from catalog import lists, reset, services
from conftest import PASSWORD, load_tmdb_fixture

URL = reverse("accounts:reset_data")


@pytest.fixture
def filled(user):
    movie = services.save_title("movie", load_tmdb_fixture("movie_155"), "de-DE").title
    watchlist = user.lists.create(name="Watchlist")
    lists.add_to_list(watchlist, movie)
    lists.mark_watched(user, movie)
    return user


def test_profile_links_to_reset(auth_client):
    content = auth_client.get(reverse("accounts:profile")).content.decode()

    assert "Gefahrenzone" in content
    assert URL in content


def test_page_shows_what_will_be_lost(auth_client, filled):
    content = auth_client.get(URL).content.decode()

    assert "1 Liste mit allen ihren Titeln" in content
    assert "1 gesehener Film" in content
    assert "0 gesehene Folgen" in content
    assert "0 gefolgte Serien" in content
    assert "Das kann nicht rückgängig gemacht werden." in content
    assert 'autocomplete="current-password"' in content


def test_correct_password_deletes_data(auth_client, filled):
    response = auth_client.post(URL, {"password": PASSWORD}, follow=True)

    assert response.redirect_chain == [(reverse("accounts:profile"), 302)]
    assert "Deine Daten wurden gelöscht." in response.content.decode()
    assert reset.user_data(filled).is_empty


@pytest.mark.parametrize("password", ["", "wrong"])
def test_wrong_password_deletes_nothing(auth_client, filled, password):
    response = auth_client.post(URL, {"password": password})

    assert response.status_code == 200
    assert not reset.user_data(filled).is_empty


def test_password_attempts_are_limited(auth_client, filled, settings):
    settings.RESET_DATA_RATE_LIMIT = 2
    for _ in range(2):
        auth_client.post(URL, {"password": "wrong"})

    response = auth_client.post(URL, {"password": PASSWORD})

    assert response.status_code == 429
    assert not reset.user_data(filled).is_empty


def test_nothing_to_delete(auth_client):
    content = auth_client.get(URL).content.decode()

    assert "Es gibt nichts zu löschen." in content
    assert 'type="password"' not in content


def test_login_required(client, db):
    response = client.get(URL)

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]
