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
    assert content.index("Dark</strong>") < content.index("The Dark Knight</strong>")
    assert "/posters/w185/54WAzARB0rTp5L7gvCcfZ49AgkX.jpg" in content
    assert movie.get_absolute_url() in content
    assert "watched-corner" in content
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
    assert "The Dark Knight" not in response.content.decode()


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
