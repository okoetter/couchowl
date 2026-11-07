"""Lists and movies in a real browser: search -> add to list -> watched -> remove."""

import re

import pytest
from playwright.sync_api import expect

from conftest import load_tmdb_fixture
from e2e.conftest import login

pytestmark = pytest.mark.e2e


def test_search_add_to_list_mark_watched_and_remove(live_server, member, page, fake_tmdb):
    fake_tmdb.add("/3/search/multi", json=load_tmdb_fixture("search_multi"))
    fake_tmdb.add("/3/movie/155", json=load_tmdb_fixture("movie_155"))
    for size in ("w92", "w185", "w342", "w500"):
        fake_tmdb.add_image(size, "54WAzARB0rTp5L7gvCcfZ49AgkX.jpg")
    url = live_server.url
    login(page, url, "anna")

    # Search and add "The Dark Knight" with the "+" button: the first list is created
    page.goto(f"{url}/search/")
    search = page.get_by_placeholder("Film oder Serie")
    search.press_sequentially("dark")
    # Typing on updates the results with "morph": entries that stay keep their poster
    poster = page.locator(".search-results img").first.element_handle()
    with page.expect_response(lambda response: "/search/?q=dark%20k" in response.url):
        search.press_sequentially(" k")
    page.wait_for_load_state("networkidle")
    assert poster.evaluate("img => img.isConnected")
    # The menu still loads after the results were updated
    page.get_by_role("button", name="„The Dark Knight“ zu einer Liste hinzufügen").click()
    # Wait for the server's answer: it replaces the menu (typing earlier would be lost)
    with page.expect_response(lambda response: "/lists/new/" in response.url):
        page.get_by_label("Watchlist").check()
    expect(page.get_by_label("Watchlist")).to_be_checked()
    # A second list, created right in the menu
    page.get_by_placeholder("Neue Liste").fill("Mit Familie")
    page.get_by_role("button", name="Liste anlegen").click()
    expect(page.get_by_label("Mit Familie")).to_be_checked()

    # Both lists exist and contain the movie
    page.get_by_role("link", name="Listen").click()
    expect(page.get_by_text("Mit Familie")).to_be_visible()
    page.get_by_role("link", name="Watchlist").click()
    page.get_by_role("link", name="The Dark Knight").click()

    # Mark as watched and change the date
    page.get_by_role("button", name="Als gesehen markieren").click()
    expect(page.get_by_text("✓ Gesehen")).to_be_visible()
    page.get_by_text("(ändern)").click()
    page.get_by_label("Gesehen am").fill("2024-03-15")
    page.get_by_role("button", name="Datum speichern").click()
    expect(page.get_by_text("am 15. März 2024")).to_be_visible()

    # Back on the list: filter "watched", undo with the button on the poster
    page.go_back()
    page.reload()
    page.get_by_role("button", name="Gesehen", exact=True).click()
    expect(page).to_have_url(re.compile(r"\?status=watched$"))
    page.get_by_role("button", name="„The Dark Knight“ als nicht gesehen markieren").click()
    expect(page.get_by_text("Keine Titel für diesen Filter.")).to_be_visible()
    page.get_by_role("link", name="Alle anzeigen").click()
    poster = page.locator(".poster-grid img").first.element_handle()
    # Filtering keeps the entries that stay visible (no poster flicker)
    page.get_by_role("button", name="Filme").click()
    expect(page).to_have_url(re.compile(r"\?type=movie$"))
    assert poster.evaluate("img => img.isConnected")
    page.get_by_role("button", name="„The Dark Knight“ als gesehen markieren").click()
    expect(
        page.get_by_role("button", name="„The Dark Knight“ als nicht gesehen markieren")
    ).to_be_visible()
    # Only the button was replaced: the poster is still the same element (no flicker)
    assert poster.evaluate("img => img.isConnected")

    # Compact view, then remove the movie from the list
    page.get_by_role("button", name="Kompakte Liste").click()
    page.get_by_role("button", name="„The Dark Knight“ von der Liste entfernen").click()
    expect(page.get_by_text("Diese Liste ist leer.")).to_be_visible()
