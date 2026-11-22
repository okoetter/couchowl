import pytest
from django.urls import reverse

from catalog import reset, services
from catalog.lists import add_to_list
from catalog.models import WatchedMovie
from conftest import load_tmdb_fixture
from imports.models import Import, ImportLine

PAGE = reverse("imports:page")
STEP = reverse("imports:step")
HTMX = {"HTTP_HX_REQUEST": "true"}


def paste(client, lines, **options):
    data = {"lines": "\n".join(lines), "target": "new", "new_list": "Imported", **options}
    return client.post(PAGE, data)


def run_steps(client):
    """Call the step endpoint like the page does, until it reloads the page."""
    for _ in range(20):
        response = client.post(STEP, **HTMX)
        if "HX-Redirect" in response:
            return response
    raise AssertionError("The import didn't finish")


def test_paste_form(auth_client, user):
    watchlist = user.lists.create(name="Watchlist")

    content = auth_client.get(PAGE, {"list": watchlist.pk}).content.decode()

    assert "Titel importieren" in content
    assert f'<option value="{watchlist.pk}" selected>Watchlist</option>' in content
    assert "Lässt sich vor dem Import pro Serie ändern." in content


@pytest.mark.parametrize(
    ("data", "error"),
    [
        ({"lines": " \n- \n", "target": "", "watched": "on"}, "Füge mindestens einen Titel ein."),
        ({"lines": "Dark", "target": "new", "new_list": " "}, "Gib einen Namen für die neue Liste"),
        ({"lines": "Dark", "target": ""}, "hat der Import nichts zu tun"),
        ({"lines": "x\n" * 501, "target": "new", "new_list": "A"}, "dies sind 501 Zeilen"),
    ],
)
def test_paste_form_errors(auth_client, data, error):
    response = auth_client.post(PAGE, data)

    assert response.status_code == 200
    assert error in response.content.decode()
    assert not Import.objects.exists()


def test_whole_import(auth_client, user, searches):
    response = paste(auth_client, ["- The Dark Knight", "Dark", "Nope"], watched="on")
    assert response.status_code == 302

    content = auth_client.get(PAGE).content.decode()
    assert 'hx-trigger="load"' in content
    assert "0 von 3 Zeilen" in content

    response = run_steps(auth_client)
    assert response["HX-Redirect"] == PAGE
    content = auth_client.get(PAGE).content.decode()
    assert "Treffer prüfen" in content
    assert "1 Zeile braucht noch eine Auswahl." in content
    assert "1 Titel importieren" in content
    assert "Wird importiert" in content

    dark = ImportLine.objects.get(text="Dark")
    response = auth_client.post(
        reverse("imports:line", args=[dark.pk]), {"choice": "tv-70523"}, **HTMX
    )
    content = response.content.decode()
    assert f'id="line-{dark.pk}"' in content
    assert 'id="import-summary" class="import-summary" hx-swap-oob="true"' in content
    assert "2 Titel importieren" in content

    response = auth_client.post(reverse("imports:start"))
    assert response.status_code == 302
    run_steps(auth_client)

    content = auth_client.get(PAGE).content.decode()
    assert "Import abgeschlossen" in content
    assert "<strong>2</strong> Titel importiert" in content
    assert ">Nope</textarea>" in content
    assert "„Imported“ öffnen" in content
    assert user.lists.get(name="Imported").items.count() == 2
    assert WatchedMovie.objects.filter(user=user, watched_at=None).exists()

    response = auth_client.post(reverse("imports:discard"))
    assert response.status_code == 302
    assert not Import.objects.exists()
    assert user.lists.get(name="Imported").items.count() == 2


def test_result_lists_skipped_lines_with_reason(auth_client, searches):
    paste(auth_client, ["The Dark Knight", "The Dark Knight (2008)", "Dark"])
    run_steps(auth_client)
    dark = ImportLine.objects.get(text="Dark")
    auth_client.post(reverse("imports:line", args=[dark.pk]), {"choice": "skip"})
    auth_client.post(reverse("imports:start"))
    run_steps(auth_client)

    content = auth_client.get(PAGE).content.decode()

    assert "2 übersprungen" in content
    assert '<a href="/movie/155/">The Dark Knight (2008)</a>' in content
    assert "wie Zeile 1" in content
    assert "von dir übersprungen" in content


def test_step_tmdb_error_offers_try_again(auth_client, searches, fake_tmdb):
    paste(auth_client, ["Dark"])
    fake_tmdb.add("/3/search/multi", json={}, status=503)

    response = auth_client.post(STEP, **HTMX)

    content = response.content.decode()
    assert "TMDB ist gerade nicht erreichbar." in content
    assert "Erneut versuchen" in content
    assert 'hx-trigger="load' not in content


def test_step_without_javascript(auth_client, searches):
    paste(auth_client, ["Dark"])

    response = auth_client.post(STEP)

    assert response.status_code == 302
    assert response["Location"] == PAGE
    assert Import.objects.get().state == Import.State.PREVIEW


def test_watched_switch_and_search_again(auth_client, searches):
    paste(auth_client, ["Dark Knigth"])
    run_steps(auth_client)
    line = ImportLine.objects.get()
    url = reverse("imports:line", args=[line.pk])

    content = auth_client.post(url, {"query": "The Dark Knight"}, **HTMX).content.decode()
    assert "Gesucht nach „The Dark Knight“" in content
    auth_client.post(url, {"watched": ["0", "1"]}, **HTMX)
    line.refresh_from_db()
    assert line.watched
    assert line.choice == "movie-155"

    auth_client.post(url, {"watched": "0"})  # without JavaScript
    line.refresh_from_db()
    assert not line.watched
    # A movie can't be followed: no switch
    assert 'name="follow"' not in content


def test_follow_switch_for_shows(auth_client, searches):
    paste(auth_client, ["Dark (2017)"])
    run_steps(auth_client)
    line = ImportLine.objects.get()
    assert not line.follow

    url = reverse("imports:line", args=[line.pk])
    content = auth_client.post(url, {"watched": "0", "follow": ["0", "1"]}, **HTMX)
    content = content.content.decode()

    assert 'name="follow" value="1" checked' in content
    line.refresh_from_db()
    assert line.follow


def test_other_users_lines_dont_exist(client, other_user, user, searches):
    from imports import rules

    batch = rules.create_import(user, ["Dark"], list_name="", watched=True, follow=False)
    client.force_login(other_user)

    response = client.post(reverse("imports:line", args=[batch.lines.get().pk]), {"choice": "skip"})

    assert response.status_code == 404


def test_reset_my_data_deletes_the_import(user):
    from imports import rules

    rules.create_import(user, ["Dark"], list_name="", watched=True, follow=False)

    reset.reset_user_data(user)

    assert not Import.objects.exists()


def test_links_to_the_import(auth_client, user):
    watchlist = user.lists.create(name="Watchlist")
    family = user.lists.create(name="Family")
    add_to_list(family, services.save_title("movie", load_tmdb_fixture("movie_155"), "de-DE").title)

    assert PAGE in auth_client.get(reverse("catalog:search")).content.decode()
    # An empty list offers the import with the list preselected
    assert (
        f"{PAGE}?list={watchlist.pk}"
        in auth_client.get(watchlist.get_absolute_url()).content.decode()
    )
    # No links in the lists' headers: an import doesn't always go into a list
    assert PAGE not in auth_client.get(reverse("catalog:lists")).content.decode()
    assert PAGE not in auth_client.get(family.get_absolute_url()).content.decode()


@pytest.fixture
def other_user(db):
    from accounts.models import User
    from conftest import PASSWORD

    return User.objects.create_user(username="eve", password=PASSWORD, region="DE")
