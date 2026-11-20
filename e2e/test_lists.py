"""Lists and movies in a real browser: search -> add to list -> watched -> remove."""

import re

import pytest
from playwright.sync_api import expect

from conftest import load_tmdb_fixture
from e2e.conftest import LOCALE, login

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

    # Compact view, then remove the movie from the list in edit mode
    page.get_by_role("button", name="Kompakte Liste").click()
    remove = page.get_by_role("button", name="„The Dark Knight“ von der Liste entfernen")
    expect(remove).to_be_hidden()
    page.get_by_role("button", name="Bearbeiten").click()
    remove.click()
    expect(page.get_by_text("Diese Liste ist leer.")).to_be_visible()


def test_edit_mode(live_server, member, page, fake_tmdb):
    """ "Edit" swaps the watched buttons for trash buttons; removing offers "Undo"; filters
    and the layout toggle keep the mode, "Done" ends it."""
    from e2e.test_screenshots import sample_lists, show_list_grid

    sample_lists(fake_tmdb, member)
    show_list_grid(page, live_server.url)
    watched = page.get_by_role("button", name="„Arrival“ als nicht gesehen markieren")
    remove_heat = page.get_by_role("button", name="„Heat“ von der Liste entfernen")
    hint = page.get_by_text("Gesehen-Status, Fortschritt und gefolgte Serien bleiben.")
    expect(watched).to_be_visible()
    expect(remove_heat).to_be_hidden()
    expect(hint).to_be_hidden()

    page.get_by_role("button", name="Bearbeiten").click()
    expect(watched).to_be_hidden()
    expect(hint).to_be_visible()
    names = page.locator(".poster-grid strong")
    before = names.all_text_contents()
    remove_heat.click()
    expect(page.locator(".poster-grid strong", has_text="Heat")).to_have_count(0)
    # "Undo" puts it back at its old place; edit mode stays
    toast = page.locator(".toast")
    expect(toast).to_contain_text("„Heat“ entfernt")
    toast.get_by_role("button", name="Rückgängig").click()
    expect(names).to_have_text(before)
    expect(toast).to_have_count(0)
    remove_heat.click()
    expect(page.locator(".poster-grid strong", has_text="Heat")).to_have_count(0)
    # A filter and the other layout keep edit mode
    page.get_by_role("button", name="Filme").click()
    expect(page).to_have_url(re.compile(r"\?type=movie$"))
    page.get_by_role("button", name="Kompakte Liste").click()
    expect(page.get_by_role("button", name="„Arrival“ von der Liste entfernen")).to_be_visible()
    expect(watched).to_be_hidden()

    page.get_by_role("button", name="Fertig").click()
    expect(watched).to_be_visible()
    expect(page.get_by_role("button", name="„Arrival“ von der Liste entfernen")).to_be_hidden()
    expect(page.get_by_role("button", name="Bearbeiten")).to_be_visible()


@pytest.mark.parametrize(
    ("width", "text_size"),
    [(320, "100%"), (360, "100%"), (390, "100%"), (360, "125%"), (412, "125%")],
)
def test_compact_list_text_stays_left_of_the_buttons_on_phones(
    live_server, member, browser, fake_tmdb, width, text_size
):
    """The text (title with the bell, "Show · 2017 · ★ 8,4", "Next: S2 E3" and the
    progress bar) wraps instead of running under the round button, and the links above
    the list wrap instead of widening the page.
    (Larger text like Android's font size setting, see test_shows.py.)
    """
    from e2e.test_screenshots import sample_lists, show_list_compact

    sample_lists(fake_tmdb, member)
    context = browser.new_context(
        locale=LOCALE, viewport={"width": width, "height": 800}, is_mobile=True, has_touch=True
    )
    page = context.new_page()
    show_list_compact(page, live_server.url)
    page.add_style_tag(content=f"html {{ font-size: {text_size} !important; }}")

    rows = page.evaluate(
        """() => [...document.querySelectorAll('.compact-list li')].map(li => ({
          name: li.querySelector('strong').firstChild.textContent.trim(),
          textEnd: li.querySelector('.result-link > div').getBoundingClientRect().right,
          buttonStart: li.querySelector('.watched-toggle').getBoundingClientRect().left,
        }))"""
    )
    assert any(row["name"] == "Dark" for row in rows)
    for row in rows:
        assert row["textEnd"] <= row["buttonStart"], row["name"]
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow == 0
    context.close()


def test_poster_opens_large_on_the_detail_page(live_server, member, page, fake_tmdb):
    fake_tmdb.add("/3/movie/155", json=load_tmdb_fixture("movie_155"))
    for size in ("w342", "w500", "w780"):
        fake_tmdb.add_image(size, "54WAzARB0rTp5L7gvCcfZ49AgkX.jpg")
    login(page, live_server.url, "anna")
    page.goto(f"{live_server.url}/movie/155/")
    enlarge = page.get_by_role("link", name="Poster vergrößern")
    dialog = page.get_by_role("dialog", name="Poster")

    enlarge.click()
    expect(dialog).to_be_visible()
    # The small image first, then the large one once it has loaded
    expect(dialog.locator("img")).to_have_attribute("src", re.compile(r"/posters/w780/"))
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    # Closing also left the dialog's history entry: none piles up
    page.wait_for_function("history.state === null")  # history.back() is asynchronous

    # The back button closes it (and stays on the page), forward opens it again
    enlarge.click()
    expect(dialog).to_be_visible()
    page.go_back()
    expect(dialog).to_be_hidden()
    assert page.url.endswith("/movie/155/")
    page.go_forward()
    expect(dialog).to_be_visible()
    # Still open after a reload (the entry is current), so "back" doesn't seem to do nothing
    page.reload()
    expect(dialog).to_be_visible()

    # A click on the image closes it too
    dialog.locator("img").click()
    expect(dialog).to_be_hidden()
    page.wait_for_function("history.state === null")  # history.back() is asynchronous
