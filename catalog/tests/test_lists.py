"""Lists: create, rename, delete, add and remove titles, layout, access control."""

import re

import pytest
from django.urls import reverse

from catalog import lists as list_rules
from catalog.models import ListItem, UserList
from conftest import load_tmdb_fixture

HTMX = {"HX-Request": "true"}
LISTS = reverse("catalog:lists")


def membership_url(title, user_list):
    return reverse(
        "catalog:title_list_membership", args=[title.media_type, title.tmdb_id, user_list.pk]
    )


def create_url(media_type, tmdb_id):
    return reverse("catalog:title_list_create", args=[media_type, tmdb_id])


# --- Lists page ------------------------------------------------------------------------------


def test_lists_page_without_lists(auth_client):
    response = auth_client.get(LISTS)

    content = response.content.decode()
    assert response.status_code == 200
    assert "noch keine Listen" in content
    assert 'name="name"' in content


def test_lists_are_sorted_by_name_and_show_their_size(auth_client, user, movie, show):
    family = user.lists.create(name="mit")
    watchlist = user.lists.create(name="Watch")
    user.lists.create(name="Animation")
    list_rules.add_to_list(watchlist, movie)
    list_rules.add_to_list(watchlist, show)
    list_rules.add_to_list(family, movie)

    content = auth_client.get(LISTS).content.decode()

    names = [content.index(f"<strong>{name}</strong>") for name in ("Animation", "mit", "Watch")]
    assert names == sorted(names)
    assert "0 Titel" in content
    assert "1 Titel" in content
    assert "2 Titel" in content


def test_create_list(auth_client, user):
    response = auth_client.post(LISTS, {"name": "  Mit   Familie "})

    new_list = user.lists.get()
    assert new_list.name == "Mit Familie"
    assert response.status_code == 302
    assert response["Location"] == new_list.get_absolute_url()


def test_list_names_are_unique_per_user_ignoring_case(auth_client, user, other_user):
    user.lists.create(name="Watchlist")
    other_user.lists.create(name="Favoriten")

    response = auth_client.post(LISTS, {"name": "watchlist"})
    assert response.status_code == 200
    assert "schon eine Liste mit diesem Namen" in response.content.decode()

    # Another user's list name doesn't matter
    auth_client.post(LISTS, {"name": "Favoriten"})
    assert sorted(user.lists.values_list("name", flat=True)) == ["Favoriten", "Watchlist"]


def test_list_name_is_required(auth_client, user):
    response = auth_client.post(LISTS, {"name": "   "})

    assert response.status_code == 200
    assert not user.lists.exists()


# --- List page -------------------------------------------------------------------------------


def test_empty_list_links_to_search(auth_client, user):
    user_list = user.lists.create(name="Watchlist")

    content = auth_client.get(user_list.get_absolute_url()).content.decode()

    assert "Diese Liste ist leer" in content
    assert reverse("catalog:search") in content


def test_list_shows_titles_newest_first_as_poster_grid(auth_client, user, movie, show):
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, movie)
    list_rules.add_to_list(user_list, show)
    list_rules.mark_watched(user, movie)

    content = auth_client.get(user_list.get_absolute_url()).content.decode()

    assert 'class="poster-grid"' in content
    assert "{#" not in content  # no template comment leaked into the page
    assert content.index("Dark</strong>") < content.index("The Dark Knight</strong>")
    assert "/posters/w185/54WAzARB0rTp5L7gvCcfZ49AgkX.jpg" in content
    assert movie.get_absolute_url() in content
    assert "watched-toggle-corner" in content
    assert "„The Dark Knight“ als nicht gesehen markieren" in content
    assert "Serie · 2017" in content


def test_list_uses_closest_stored_language(auth_client, user):
    """Lists never ask TMDB; a missing language falls back to a stored one."""
    from catalog import services

    data = load_tmdb_fixture("movie_155")
    french = services.save_title("movie", data, "fr-FR").title
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, french)

    content = auth_client.get(user_list.get_absolute_url()).content.decode()

    assert "The Dark Knight : Le Chevalier noir" in content


def test_layout_is_saved_per_user(auth_client, user, movie):
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, movie)
    url = reverse("catalog:list_layout", args=[user_list.pk])

    response = auth_client.post(url, {"layout": "compact"}, headers=HTMX)

    user.refresh_from_db()
    assert user.list_layout == "compact"
    content = response.content.decode()
    assert "<html" not in content
    assert 'class="compact-list"' in content
    pressed = re.search(r'value="(\w+)"\s+class="[^"]*" aria-pressed="true"', content)
    assert pressed.group(1) == "compact"

    # Without JavaScript: redirect back to the list
    response = auth_client.post(url, {"layout": "grid"})
    assert response["Location"] == user_list.get_absolute_url()
    user.refresh_from_db()
    assert user.list_layout == "grid"


def test_unknown_layout_is_ignored(auth_client, user):
    user_list = user.lists.create(name="Watchlist")

    auth_client.post(reverse("catalog:list_layout", args=[user_list.pk]), {"layout": "huge"})

    user.refresh_from_db()
    assert user.list_layout == "grid"


def test_remove_item_from_compact_list(auth_client, user, movie, show):
    user.list_layout = "compact"
    user.save()
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, movie)
    list_rules.add_to_list(user_list, show)
    item = user_list.items.get(title=movie)

    content = auth_client.get(user_list.get_absolute_url()).content.decode()
    assert reverse("catalog:list_item_remove", args=[user_list.pk, item.pk]) in content

    response = auth_client.post(
        reverse("catalog:list_item_remove", args=[user_list.pk, item.pk]), headers=HTMX
    )

    assert list(user_list.items.values_list("title", flat=True)) == [show.pk]
    # Only the message, no entry
    assert "<li" not in response.content.decode()


@pytest.mark.parametrize("layout", ["grid", "compact"])
def test_edit_mode_offers_remove_buttons(auth_client, user, movie, layout):
    """The trash buttons are always rendered; CSS shows them instead of the watched
    buttons once "Edit" is clicked (a class on #list-content, see list_detail.html)."""
    user.list_layout = layout
    user.save()
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, movie)
    item = user_list.items.get()

    content = auth_client.get(user_list.get_absolute_url()).content.decode()

    assert '<div id="list-content" x-data="{ editing: false }"' in content
    assert '@click="editing = !editing"' in content
    assert "Entfernt Titel nur aus dieser Liste – Gesehen-Status, Fortschritt" in content
    form = content.split(
        f'action="{reverse("catalog:list_item_remove", args=[user_list.pk, item.pk])}"'
    )
    assert len(form) == 2
    assert ("remove-form-corner" in form[0].rsplit("<form", 1)[1]) == (layout == "grid")
    assert "„The Dark Knight“ von der Liste entfernen" in content


def test_rename_list(auth_client, user):
    user_list = user.lists.create(name="Watchlist")
    user.lists.create(name="Favoriten")
    url = reverse("catalog:list_rename", args=[user_list.pk])

    assert 'value="Watchlist"' in auth_client.get(url).content.decode()

    response = auth_client.post(url, {"name": "favoriten"})
    assert "schon eine Liste mit diesem Namen" in response.content.decode()

    # Changing only the case of the own name is fine
    response = auth_client.post(url, {"name": "WATCHLIST"})
    assert response["Location"] == user_list.get_absolute_url()
    user_list.refresh_from_db()
    assert user_list.name == "WATCHLIST"


def test_delete_list_asks_first_and_keeps_watched_state(auth_client, user, movie):
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, movie)
    list_rules.mark_watched(user, movie)
    url = reverse("catalog:list_delete", args=[user_list.pk])

    content = auth_client.get(url).content.decode()
    assert "„Watchlist“ mit 1 Titel löschen?" in content
    assert UserList.objects.exists()

    response = auth_client.post(url)

    assert response["Location"] == LISTS
    assert not UserList.objects.exists()
    assert not ListItem.objects.exists()
    assert user.watched_movies.filter(title=movie).exists()


@pytest.mark.parametrize(
    ("url_name", "method", "extra_args"),
    [
        ("catalog:list_detail", "get", []),
        ("catalog:list_rename", "get", []),
        ("catalog:list_rename", "post", []),
        ("catalog:list_delete", "get", []),
        ("catalog:list_delete", "post", []),
        ("catalog:list_layout", "post", []),
        ("catalog:list_item_remove", "post", ["item"]),
        ("catalog:list_item_restore", "post", []),
    ],
)
def test_other_users_lists_are_invisible(
    auth_client, other_user, movie, url_name, method, extra_args
):
    foreign = other_user.lists.create(name="Geheim")
    item = ListItem.objects.create(user_list=foreign, title=movie)
    args = [foreign.pk] + [item.pk for _ in extra_args]

    response = getattr(auth_client, method)(reverse(url_name, args=args), {"name": "Meins"})

    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.name == "Geheim"
    assert foreign.items.count() == 1


def test_other_users_lists_are_not_listed(auth_client, other_user):
    other_user.lists.create(name="Geheim")

    assert "Geheim" not in auth_client.get(LISTS).content.decode()


# --- "Add to list" menu ------------------------------------------------------------------------


def test_menu_shows_lists_with_membership(auth_client, user, movie):
    watchlist = user.lists.create(name="Watchlist")
    user.lists.create(name="Favoriten")
    list_rules.add_to_list(watchlist, movie)

    response = auth_client.get(reverse("catalog:title_lists", args=["movie", 155]), headers=HTMX)

    content = response.content.decode()
    assert "<html" not in content
    assert f'id="list-movie-155-{watchlist.pk}"\n               checked' in content
    assert content.count("checked") == 1
    assert "Favoriten" in content


def test_menu_offers_a_watchlist_when_there_are_no_lists(auth_client, fake_tmdb):
    response = auth_client.get(reverse("catalog:title_lists", args=["tv", 70523]), headers=HTMX)

    content = response.content.decode()
    assert 'value="Watchlist"' in content
    assert create_url("tv", 70523) in content
    # Opening the menu costs no TMDB request, even for titles that aren't stored yet
    assert fake_tmdb.requests == []


def test_add_and_remove_with_checkbox(auth_client, user, movie):
    user_list = user.lists.create(name="Watchlist")

    response = auth_client.post(membership_url(movie, user_list), {"member": "1"}, headers=HTMX)
    assert user_list.items.filter(title=movie).exists()
    assert "checked" in response.content.decode()

    # Adding twice changes nothing
    auth_client.post(membership_url(movie, user_list), {"member": "1"}, headers=HTMX)
    assert user_list.items.count() == 1

    response = auth_client.post(membership_url(movie, user_list), {}, headers=HTMX)
    assert not user_list.items.exists()
    assert "checked" not in response.content.decode()


def test_adding_loads_the_title_from_tmdb(auth_client, user, fake_tmdb):
    fake_tmdb.add("/3/tv/70523", json=load_tmdb_fixture("tv_70523"))
    user_list = user.lists.create(name="Watchlist")

    auth_client.post(
        reverse("catalog:title_list_membership", args=["tv", 70523, user_list.pk]),
        {"member": "1"},
        headers=HTMX,
    )

    item = user_list.items.get()
    assert item.title.original_title == "Dark"
    assert item.title.translations.get().language == "de-DE"


def test_adding_unknown_title_is_404(auth_client, user, fake_tmdb):
    fake_tmdb.add("/3/movie/999", json={}, status=404)
    user_list = user.lists.create(name="Watchlist")

    response = auth_client.post(
        reverse("catalog:title_list_membership", args=["movie", 999, user_list.pk]),
        {"member": "1"},
    )

    assert response.status_code == 404
    assert not user_list.items.exists()


def test_adding_while_tmdb_is_down_shows_error_in_menu(auth_client, user, fake_tmdb):
    fake_tmdb.add("/3/movie/155", json={}, status=503)
    user_list = user.lists.create(name="Watchlist")

    response = auth_client.post(
        reverse("catalog:title_list_membership", args=["movie", 155, user_list.pk]),
        {"member": "1"},
        headers=HTMX,
    )

    assert response.status_code == 200  # htmx only swaps successful responses
    assert "TMDB ist gerade nicht erreichbar" in response.content.decode()
    assert not user_list.items.exists()


def test_cannot_add_to_other_users_list(auth_client, other_user, movie):
    foreign = other_user.lists.create(name="Geheim")

    response = auth_client.post(membership_url(movie, foreign), {"member": "1"})

    assert response.status_code == 404
    assert not foreign.items.exists()


def test_first_add_creates_the_watchlist(auth_client, user, movie):
    response = auth_client.post(create_url("movie", 155), {"name": "Watchlist"}, headers=HTMX)

    watchlist = user.lists.get()
    assert watchlist.name == "Watchlist"
    assert watchlist.items.get().title == movie
    assert "checked" in response.content.decode()


def test_new_list_from_menu_reuses_an_existing_name(auth_client, user, movie):
    existing = user.lists.create(name="Favoriten")

    auth_client.post(create_url("movie", 155), {"name": " favoriten "}, headers=HTMX)

    assert user.lists.get() == existing
    assert existing.items.get().title == movie


def test_new_list_from_menu_needs_a_name(auth_client, user, movie):
    response = auth_client.post(create_url("movie", 155), {"name": " "}, headers=HTMX)

    assert "Bitte gib einen Namen ein" in response.content.decode()
    assert not user.lists.exists()

    auth_client.post(create_url("movie", 155), {"name": "x" * 101}, headers=HTMX)
    assert not user.lists.exists()


def test_find_or_create_list_normalizes_whitespace(user):
    created = list_rules.find_or_create_list(user, "  Mit   Familie ")

    assert created.name == "Mit Familie"
    assert list_rules.find_or_create_list(user, "mit familie") == created


# --- Filters -----------------------------------------------------------------------------------


@pytest.fixture
def mixed_list(user, movie, show):
    """Watchlist with a watched movie, an unwatched movie and a show."""
    from catalog import services

    data = load_tmdb_fixture("movie_155")
    data.update(id=156, original_title="Heat")
    for translation in data["translations"]["translations"]:
        translation["data"]["title"] = ""
    heat = services.save_title("movie", data, "de-DE").title
    user_list = user.lists.create(name="Watchlist")
    for title in (movie, heat, show):
        list_rules.add_to_list(user_list, title)
    list_rules.mark_watched(user, movie)
    return user_list


def shown_names(content):
    return re.findall(r"<strong>([^<]+)</strong>", content.split('id="list-content"')[-1])


@pytest.mark.parametrize(
    ("query", "names"),
    [
        ({}, ["Dark", "Heat", "The Dark Knight"]),
        ({"status": "watched"}, ["The Dark Knight"]),
        # Shows count as unwatched until episode tracking exists
        ({"status": "unwatched"}, ["Dark", "Heat"]),
        ({"type": "movie"}, ["Heat", "The Dark Knight"]),
        ({"type": "tv"}, ["Dark"]),
        ({"status": "unwatched", "type": "movie"}, ["Heat"]),
        ({"status": "nonsense", "type": "person"}, ["Dark", "Heat", "The Dark Knight"]),
    ],
)
def test_filters(auth_client, mixed_list, query, names):
    content = auth_client.get(mixed_list.get_absolute_url(), query).content.decode()

    assert shown_names(content) == names


def test_filter_links_keep_the_other_filter(auth_client, mixed_list):
    url = mixed_list.get_absolute_url()

    content = auth_client.get(url, {"type": "movie"}).content.decode()

    assert f'href="{url}?status=unwatched&amp;type=movie"' in content
    assert f'href="{url}"' in content  # "All" + "All" = no filter
    assert f'href="{url}?type=movie" role="button"' in content


def test_filter_with_htmx_returns_only_the_content(auth_client, mixed_list):
    response = auth_client.get(mixed_list.get_absolute_url(), {"type": "tv"}, headers=HTMX)

    content = response.content.decode()
    assert "<html" not in content
    assert shown_names(content) == ["Dark"]
    assert "HX-Request" in response["Vary"]


def test_empty_filter_result_offers_all(auth_client, user, show):
    user_list = user.lists.create(name="Serien")
    list_rules.add_to_list(user_list, show)

    content = auth_client.get(user_list.get_absolute_url(), {"status": "watched"}).content
    content = content.decode()

    assert "Keine Titel für diesen Filter." in content
    assert "Alle anzeigen" in content


def test_actions_keep_the_filter(auth_client, user, mixed_list):
    item = mixed_list.items.get(title__original_title="Heat")
    url = reverse("catalog:list_item_watched", args=[mixed_list.pk, item.pk])

    content = auth_client.get(mixed_list.get_absolute_url(), {"status": "unwatched"}).content
    assert f'{url}?status=unwatched"' in content.decode()

    # Marking an unwatched movie as watched hides it in the "unwatched" view:
    # htmx removes just this entry
    response = auth_client.post(f"{url}?status=unwatched", {"watched": "1"}, headers=HTMX)
    assert response.content == b""
    assert response["HX-Retarget"] == "closest li"
    assert response["HX-Reswap"] == "outerHTML"

    # Without JavaScript: back to the filtered list
    response = auth_client.post(f"{url}?status=unwatched", {})
    assert response["Location"] == f"{mixed_list.get_absolute_url()}?status=unwatched"


# --- Watched button on the list page -------------------------------------------------------------


def test_watched_button_marks_today_and_undoes(auth_client, user, movie):
    from django.utils import timezone

    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, movie)
    item = user_list.items.get()
    url = reverse("catalog:list_item_watched", args=[user_list.pk, item.pk])

    response = auth_client.post(url, {"watched": "1"}, headers=HTMX)
    assert user.watched_movies.get(title=movie).watched_at == timezone.localdate()
    assert 'aria-pressed="true"' in response.content.decode()

    auth_client.post(url, {}, headers=HTMX)
    assert not user.watched_movies.exists()


def test_watched_button_keeps_an_existing_date(auth_client, user, movie):
    from datetime import date

    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, movie)
    list_rules.mark_watched(user, movie, date(2020, 5, 1))
    url = reverse("catalog:list_item_watched", args=[user_list.pk, user_list.items.get().pk])

    auth_client.post(url, {"watched": "1"}, headers=HTMX)

    assert user.watched_movies.get(title=movie).watched_at == date(2020, 5, 1)


def test_shows_show_their_progress(auth_client, user, show):
    from catalog import shows

    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, show)
    item = user_list.items.get()
    url = reverse("catalog:list_item_watched", args=[user_list.pk, item.pk])
    first = show.seasons.get(number=1).episodes.get(number=1)
    shows.mark_episode(user, first)

    content = auth_client.get(user_list.get_absolute_url()).content.decode()

    assert url in content
    assert "1 von 26 Folgen gesehen" in content
    assert "S1 E2 von „Dark“ als gesehen markieren" in content


def test_show_button_marks_the_next_episode_with_undo(auth_client, user, show):
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, show)
    item = user_list.items.get()
    url = reverse("catalog:list_item_watched", args=[user_list.pk, item.pk])

    content = auth_client.post(url, {"next": "1"}, headers=HTMX).content.decode()

    watched = user.watched_episodes.get()
    assert watched.episode.code == "S1 E1"
    assert "1 von 26 Folgen gesehen" in content
    assert "<img" not in content
    # Message with "undo" in the toast region
    assert 'hx-swap-oob="innerHTML:#toast"' in content
    assert "S1 E1 gesehen" in content
    assert f'name="undo" value="{watched.episode.pk}"' in content

    content = auth_client.post(url, {"undo": watched.episode.pk}, headers=HTMX).content.decode()

    assert not user.watched_episodes.exists()
    assert "S1 E1 von „Dark“ als gesehen markieren" in content  # whole content, button as before
    assert "S1 E1 gesehen" not in content


def test_show_button_without_javascript(auth_client, user, show):
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, show)
    url = reverse("catalog:list_item_watched", args=[user_list.pk, user_list.items.get().pk])

    response = auth_client.post(url, {"next": "1"}, follow=True)

    assert "S1 E1 gesehen." in response.content.decode()


def test_undo_only_accepts_episodes_of_this_show(auth_client, user, show, movie):
    from catalog.models import Episode

    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, show)
    url = reverse("catalog:list_item_watched", args=[user_list.pk, user_list.items.get().pk])

    response = auth_client.post(url, {"undo": Episode.objects.latest("pk").pk + 1})

    assert response.status_code == 404


def test_completely_watched_show_counts_as_watched(auth_client, user, mixed_list, show):
    from catalog import shows

    for season in show.seasons.all():
        shows.mark_season(user, season)

    content = auth_client.get(mixed_list.get_absolute_url(), {"status": "watched"}).content
    content = content.decode()

    assert shown_names(content) == ["Dark", "The Dark Knight"]
    assert "26 von 26 Folgen gesehen" in content


def test_completely_watched_show_can_be_marked_as_not_watched(auth_client, user, show):
    from catalog import shows

    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, show)
    url = reverse("catalog:list_item_watched", args=[user_list.pk, user_list.items.get().pk])
    for season in show.seasons.all():
        shows.mark_season(user, season)

    content = auth_client.get(user_list.get_absolute_url()).content.decode()
    # A misclick would delete all dates: asks first
    assert "Alle Folgen von „Dark“ als nicht gesehen markieren?" in content
    assert 'name="unwatched"' in content

    content = auth_client.post(url, {"unwatched": "1"}, headers=HTMX).content.decode()

    assert not user.watched_episodes.exists()
    assert "0 von 26 Folgen gesehen" in content
    assert "<img" not in content
    assert 'hx-swap-oob="innerHTML:#toast"' in content  # an old "Undo" disappears


def test_watched_button_on_other_users_list_is_404(auth_client, user, other_user, movie):
    foreign = other_user.lists.create(name="Geheim")
    item = ListItem.objects.create(user_list=foreign, title=movie)

    response = auth_client.post(
        reverse("catalog:list_item_watched", args=[foreign.pk, item.pk]), {"watched": "1"}
    )

    assert response.status_code == 404
    assert not user.watched_movies.exists()


# --- Small htmx updates (no flicker) ------------------------------------------------------------


def test_watched_button_answer_is_only_the_button(auth_client, user, mixed_list):
    item = mixed_list.items.get(title__original_title="Heat")
    url = reverse("catalog:list_item_watched", args=[mixed_list.pk, item.pk])

    content = auth_client.post(url, {"watched": "1"}, headers=HTMX).content.decode()

    # No poster images are sent again (rebuilding them makes the list flicker)
    assert "<img" not in content
    assert content.count("<form") == 1
    assert "watched-toggle-corner" in content
    assert "„Heat“ als nicht gesehen markieren" in content
    # Plus the (empty for movies) text below the title and progress bar, by their ids
    assert f'id="watched-badge-{item.pk}" class="next-episode" hx-swap-oob="true"' in content
    assert f'id="poster-progress-{item.pk}" class="poster-progress" hx-swap-oob="true"' in content


def test_compact_view_also_updates_the_watched_text(auth_client, user, mixed_list):
    user.list_layout = "compact"
    user.save()
    item = mixed_list.items.get(title__original_title="Heat")
    url = reverse("catalog:list_item_watched", args=[mixed_list.pk, item.pk])

    content = auth_client.post(url, {"watched": "1"}, headers=HTMX).content.decode()

    assert "watched-toggle-corner" not in content
    assert f'id="watched-badge-{item.pk}" hx-swap-oob="true"' in content
    assert "✓ Gesehen" in content


def test_removing_an_entry_removes_only_that_entry(auth_client, user, mixed_list):
    item = mixed_list.items.get(title__original_title="Heat")

    response = auth_client.post(
        reverse("catalog:list_item_remove", args=[mixed_list.pk, item.pk]), headers=HTMX
    )

    # Nothing replaces the entry, only the message goes to the #toast region
    assert response.content.decode().lstrip().startswith('<div hx-swap-oob="innerHTML:#toast">')
    assert response["HX-Retarget"] == "closest li"


def test_removing_the_last_entry_shows_the_empty_list(auth_client, user, movie):
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, movie)
    item = user_list.items.get()

    response = auth_client.post(
        reverse("catalog:list_item_remove", args=[user_list.pk, item.pk]), headers=HTMX
    )

    assert response["HX-Retarget"] == "#list-content"
    assert response["HX-Reswap"] == "innerHTML"
    assert "Diese Liste ist leer" in response.content.decode()


def test_removing_offers_undo(auth_client, user, mixed_list):
    item = mixed_list.items.get(title__original_title="Heat")

    response = auth_client.post(
        reverse("catalog:list_item_remove", args=[mixed_list.pk, item.pk]) + "?type=movie",
        headers=HTMX,
    )

    content = response.content.decode()
    assert "„Heat“ entfernt" in content
    restore = reverse("catalog:list_item_restore", args=[mixed_list.pk]) + "?type=movie"
    assert f'hx-post="{restore}"' in content
    assert f'name="title" value="{item.title_id}"' in content
    assert f'name="added_at" value="{item.added_at.isoformat()}"' in content


def test_undo_puts_the_entry_back_at_its_place(auth_client, user, mixed_list):
    item = mixed_list.items.get(title__original_title="Heat")
    before = shown_names(auth_client.get(mixed_list.get_absolute_url()).content.decode())
    auth_client.post(reverse("catalog:list_item_remove", args=[mixed_list.pk, item.pk]))

    response = auth_client.post(
        reverse("catalog:list_item_restore", args=[mixed_list.pk]),
        {"title": item.title_id, "added_at": item.added_at.isoformat()},
        headers=HTMX,
    )

    content = response.content.decode()
    assert shown_names(content) == before
    assert mixed_list.items.get(title=item.title).added_at == item.added_at
    # The message disappears
    assert '<div hx-swap-oob="innerHTML:#toast">' in content
    assert "„Heat“ entfernt" not in content


def test_undo_does_nothing_when_the_title_is_back_already(auth_client, user, mixed_list):
    item = mixed_list.items.get(title__original_title="Heat")

    response = auth_client.post(
        reverse("catalog:list_item_restore", args=[mixed_list.pk]),
        {"title": item.title_id, "added_at": "2001-01-01T00:00:00+00:00"},
    )

    assert response.status_code == 302
    assert mixed_list.items.get(title=item.title).added_at == item.added_at


def test_undo_with_invalid_data_is_rejected(auth_client, user, mixed_list):
    url = reverse("catalog:list_item_restore", args=[mixed_list.pk])

    assert auth_client.post(url, {"title": "x", "added_at": "today"}).status_code == 400
    assert mixed_list.items.count() == 3


def test_last_entry_leaving_the_filter_shows_the_filter_message(auth_client, user, movie):
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, movie)
    item = user_list.items.get()
    url = reverse("catalog:list_item_watched", args=[user_list.pk, item.pk])

    response = auth_client.post(f"{url}?status=unwatched", {"watched": "1"}, headers=HTMX)

    assert response["HX-Retarget"] == "#list-content"
    assert "Keine Titel für diesen Filter." in response.content.decode()


# --- System list "Followed shows" -----------------------------------------------------------------


FOLLOWED = reverse("catalog:list_detail", args=["followed"])


def test_followed_shows_appear_once_the_user_follows_a_show(auth_client, user, show):
    from catalog import shows

    assert "Gefolgte Serien" not in auth_client.get(LISTS).content.decode()

    shows.set_following(user, show, True)

    content = auth_client.get(LISTS).content.decode()
    assert f'href="{FOLLOWED}"' in content
    assert "1 Serie" in content
    # Set apart from the user's own lists: tinted box, bell (decorative), explanation
    assert '<li class="list-index-system">' in content
    assert 'class="icon followed-icon" aria-hidden="true"' in content
    assert "Automatisch: alle Serien, denen du folgst" in content


def test_followed_shows_can_be_hidden_in_the_profile(auth_client, user, show):
    from catalog import shows

    shows.set_following(user, show, True)
    user.show_followed_list = False
    user.save()

    assert "Gefolgte Serien" not in auth_client.get(LISTS).content.decode()


def test_followed_shows_list(auth_client, user, other_user, show):
    from catalog import shows

    shows.set_following(user, show, True)

    content = auth_client.get(FOLLOWED).content.decode()

    bell = '<svg viewBox="0 0 24 24" class="icon followed-icon" aria-hidden="true">'
    assert f"<h1>Gefolgte Serien {bell}" in content
    # A note instead of rename/delete: why, how to unfollow, link to the profile setting
    assert "Enthält alle Serien, denen du folgst. Entfolgen mit der Glocke" in content
    assert f'href="{reverse("accounts:profile")}#id_show_followed_list"' in content
    assert shown_names(content) == ["Dark"]
    assert "S1 E1 von „Dark“ als gesehen markieren" in content  # as in other lists
    # Computed list: nothing to rename, delete or remove; only shows, so no type filter
    assert "Umbenennen" not in content
    assert "aus der Liste entfernen" not in content
    assert "editing = !editing" not in content  # no "Edit" button
    assert "?type=movie" not in content
    # Every user sees their own followed shows
    auth_client.force_login(other_user)
    content = auth_client.get(FOLLOWED).content.decode()
    assert shown_names(content) == []
    assert "Du folgst keiner Serie" in content


def test_followed_shows_progress_button_works(auth_client, user, show):
    from catalog import shows

    shows.set_following(user, show, True)
    series = shows.followed_shows(user).get()
    url = reverse("catalog:list_item_watched", args=["followed", series.pk])
    assert url in auth_client.get(FOLLOWED).content.decode()

    auth_client.post(url, {"next": "1"}, headers=HTMX)

    assert user.watched_episodes.get().episode.code == "S1 E1"


def test_followed_shows_cannot_be_edited(auth_client, user, show):
    from catalog import shows

    shows.set_following(user, show, True)
    series = shows.followed_shows(user).get()

    remove = reverse("catalog:list_item_remove", args=["followed", series.pk])
    assert auth_client.post(remove).status_code == 404
    restore = reverse("catalog:list_item_restore", args=["followed"])
    assert auth_client.post(restore, {"title": show.pk}).status_code == 404
    assert auth_client.get("/lists/followed/rename/").status_code == 404
    assert auth_client.get("/lists/followed/delete/").status_code == 404
    assert shows.is_following(user, show)


def test_followed_shows_of_other_users_are_not_reachable(auth_client, other_user, show):
    from catalog import shows

    shows.set_following(other_user, show, True)
    series = shows.followed_shows(other_user).get()

    url = reverse("catalog:list_item_watched", args=["followed", series.pk])
    assert auth_client.post(url, {"next": "1"}).status_code == 404


def test_grid_shows_the_next_episode_and_the_progress_on_the_poster(auth_client, user, show):
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, show)
    item = user_list.items.get()

    content = auth_client.get(user_list.get_absolute_url()).content.decode()

    # A round check like movies, "▶ S1 E1" below the title, no bar before the first episode
    assert 'class="icon-button" aria-pressed="false"' in content
    assert 'aria-label="Als Nächstes:"><title>Als Nächstes:</title>' in content
    assert "</svg>S1 E1</span>" in content
    assert "<progress" not in content

    # After a click: text and bar are updated "out of band"
    url = reverse("catalog:list_item_watched", args=[user_list.pk, item.pk])
    content = auth_client.post(url, {"next": "1"}, headers=HTMX).content.decode()
    oob = 'hx-swap-oob="true"'
    badge = content.split(f'id="watched-badge-{item.pk}" class="next-episode" {oob}')[1]
    assert "</svg>S1 E2</span>" in badge
    bar = content.split(f'id="poster-progress-{item.pk}" class="poster-progress" {oob}')[1]
    assert '<progress value="1" max="26" title="1 von 26 Folgen gesehen" aria-hidden="true">' in bar


def test_compact_view_shows_the_next_episode(auth_client, user, show):
    user.list_layout = "compact"
    user.save()
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, show)
    item = user_list.items.get()

    content = auth_client.get(user_list.get_absolute_url()).content.decode()
    assert 'Als Nächstes: <span class="nowrap">S1 E1</span>' in content

    # A round check like movies (not the grid's "0/26" button); no progress bar yet
    assert 'class="check-button" aria-pressed="false"' in content
    assert "progress-count" not in content
    assert "<progress" not in content

    # After a click the text is updated too ("out of band"), now with the progress bar
    url = reverse("catalog:list_item_watched", args=[user_list.pk, item.pk])
    content = auth_client.post(url, {"next": "1"}, headers=HTMX).content.decode()
    badge = content.split(f'id="watched-badge-{item.pk}" hx-swap-oob="true"')[1]
    assert 'Als Nächstes: <span class="nowrap">S1 E2</span>' in badge
    assert '<progress value="1" max="26" aria-label="1 von 26 Folgen gesehen">' in badge


def follow_button(content, pk):
    """The bell form of entry `pk` (`hx-swap-oob` if updated out of band)."""
    match = re.search(rf'<form [^>]*id="follow-toggle-{pk}".*?</form>', content, re.S)
    return match.group(0) if match else None


def test_bell_follows_and_unfollows_a_show_in_the_grid(auth_client, user, show):
    from catalog import shows

    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, show)
    item = user_list.items.get()
    url = reverse("catalog:list_item_follow", args=[user_list.pk, item.pk])

    # Not followed: an empty bell on the poster that follows
    bell = follow_button(auth_client.get(user_list.get_absolute_url()).content.decode(), item.pk)
    assert 'class="follow-toggle follow-toggle-corner"' in bell
    assert f'hx-post="{url}"' in bell
    assert '<input type="hidden" name="following" value="1">' in bell
    assert 'aria-pressed="false"' in bell
    assert 'aria-label="„Dark“ folgen"' in bell

    # The answer is just the bell, now filled
    content = auth_client.post(url, {"following": "1"}, headers=HTMX).content.decode()
    assert shows.is_following(user, show)
    assert content.strip().startswith("<form")
    assert 'aria-pressed="true"' in content
    assert 'aria-label="„Dark“ nicht mehr folgen"' in content
    assert 'name="following"' not in content

    auth_client.post(url, headers=HTMX)
    assert not shows.is_following(user, show)


def test_bell_in_the_compact_view_keeps_the_filter(auth_client, user, show, mixed_list):
    from catalog import shows

    user.list_layout = "compact"
    user.save()
    item = mixed_list.items.get(title=show)
    url = reverse("catalog:list_item_follow", args=[mixed_list.pk, item.pk])

    content = auth_client.get(mixed_list.get_absolute_url()).content.decode()
    assert content.count('class="follow-toggle"') == 1  # movies have no bell

    content = auth_client.post(
        f"{url}?status=unwatched", {"following": "1"}, headers=HTMX
    ).content.decode()
    assert shows.is_following(user, show)
    assert 'class="follow-toggle"' in content
    assert 'class="check-button" aria-pressed="true"' in content
    assert f'hx-post="{url}?status=unwatched"' in content

    # Without JavaScript: back to the list with its filter
    response = auth_client.post(f"{url}?status=unwatched")
    assert response.url == f"{mixed_list.get_absolute_url()}?status=unwatched"
    assert not shows.is_following(user, show)


def test_bell_is_only_for_shows_of_own_lists(auth_client, user, other_user, movie, show):
    own = user.lists.create(name="Watchlist")
    list_rules.add_to_list(own, movie)
    movie_item = own.items.get()
    assert (
        auth_client.post(
            reverse("catalog:list_item_follow", args=[own.pk, movie_item.pk]), {"following": "1"}
        ).status_code
        == 404
    )

    foreign = other_user.lists.create(name="Eves Liste")
    list_rules.add_to_list(foreign, show)
    show_item = foreign.items.get()
    url = reverse("catalog:list_item_follow", args=[foreign.pk, show_item.pk])
    assert auth_client.post(url, {"following": "1"}).status_code == 404


def test_first_watched_episode_fills_the_bell(auth_client, user, show):
    user_list = user.lists.create(name="Watchlist")
    list_rules.add_to_list(user_list, show)
    item = user_list.items.get()

    url = reverse("catalog:list_item_watched", args=[user_list.pk, item.pk])
    content = auth_client.post(url, {"next": "1"}, headers=HTMX).content.decode()

    bell = follow_button(content, item.pk)
    assert 'hx-swap-oob="true"' in bell
    assert 'aria-pressed="true"' in bell


def test_unfollowed_show_stays_in_followed_shows_until_reload(auth_client, user, show):
    from catalog import shows

    # The first watched episode follows the show (later ones don't, after unfollowing)
    shows.mark_episode(user, show.seasons.get(number=1).episodes.get(number=1))
    series = shows.followed_shows(user).get()
    url = reverse("catalog:list_item_follow", args=["followed", series.pk])
    bell = follow_button(auth_client.get(FOLLOWED).content.decode(), series.pk)
    assert 'aria-pressed="true"' in bell

    # Unfollowed: the answer is the empty bell, the entry stays on the page
    content = auth_client.post(url, headers=HTMX).content.decode()
    assert not shows.is_following(user, show)
    assert 'aria-pressed="false"' in content
    # A second click follows again, although the show has left the list
    auth_client.post(url, {"following": "1"}, headers=HTMX)
    assert shows.is_following(user, show)

    # Its check still works; the entry then leaves the page (here the last one: "empty")
    auth_client.post(url, headers=HTMX)
    watched = reverse("catalog:list_item_watched", args=["followed", series.pk])
    response = auth_client.post(watched, {"next": "1"}, headers=HTMX)
    assert user.watched_episodes.order_by("-pk").first().episode.code == "S1 E2"
    assert "Du folgst keiner Serie" in response.content.decode()
    assert shown_names(auth_client.get(FOLLOWED).content.decode()) == []


def test_followed_shows_of_other_users_cannot_be_unfollowed(auth_client, other_user, show):
    from catalog import shows

    shows.set_following(other_user, show, True)
    series = shows.followed_shows(other_user).get()

    url = reverse("catalog:list_item_follow", args=["followed", series.pk])
    assert auth_client.post(url).status_code == 404
    assert shows.is_following(other_user, show)
