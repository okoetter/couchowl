"""Shows in a real browser: follow, mark episodes and seasons, progress button in lists."""

import pytest
from playwright.sync_api import expect

from catalog.models import WatchedEpisode
from e2e.conftest import login

pytestmark = pytest.mark.e2e


def test_follow_mark_episodes_and_watch_next_from_the_list(live_server, member, page, fake_tmdb):
    fake_tmdb.add_show()
    for size in ("w92", "w185", "w342", "w500"):
        fake_tmdb.add_image(size, "gw8ZlIXEg6SIx3FgMEQqmBkPYKV.jpg")
    url = live_server.url
    login(page, url, "anna")
    page.on("dialog", lambda dialog: dialog.accept())  # "undo the whole season?"

    page.goto(f"{url}/tv/70523/")
    expect(page.get_by_text("0 von 26 Folgen gesehen")).to_be_visible()
    # The check buttons are round (Pico once stretched them to the form's width)
    box = page.locator("#episode-1-1 .check-button").bounding_box()
    assert box["width"] == box["height"]

    # Follow: the system list appears
    page.get_by_role("button", name="Folgen", exact=True).click()
    expect(page.get_by_role("button", name="✓ Gefolgt")).to_be_visible()

    # Season 1 is open (next episode); mark episode 1, the progress line follows
    page.get_by_role("button", name="S1 E1 als gesehen markieren").click()
    expect(page.get_by_role("button", name="S1 E1 als nicht gesehen markieren")).to_be_visible()
    expect(page.get_by_text("1 von 26 Folgen gesehen")).to_be_visible()
    expect(page.locator("#show-progress")).to_contain_text("S1 E2")

    # Season 2 loads its episodes when opened; mark the whole season
    page.get_by_text("Staffel 2", exact=True).click()
    expect(page.locator("#episode-2-8")).to_be_visible()
    page.get_by_role("button", name="„Staffel 2“ als gesehen markieren").click()
    expect(page.get_by_role("button", name="S2 E8 als nicht gesehen markieren")).to_be_visible()
    expect(page.get_by_text("9 von 26 Folgen gesehen")).to_be_visible()
    # ... and undo it (after confirming)
    page.get_by_role("button", name="„Staffel 2“ als nicht gesehen markieren").click()
    expect(page.get_by_text("1 von 26 Folgen gesehen")).to_be_visible()

    # Followed shows list: the button marks the next episode, "undo" takes it back
    page.get_by_role("link", name="Listen").click()
    page.get_by_role("link", name="Gefolgte Serien").click()
    page.get_by_role("button", name="S1 E2 von „Dark“ als gesehen markieren").click()
    expect(page.get_by_text("S1 E2 gesehen")).to_be_visible()
    expect(page.get_by_text("2/26")).to_be_visible()
    page.get_by_role("button", name="Rückgängig").click()
    expect(page.get_by_text("1/26")).to_be_visible()
    expect(page.get_by_text("S1 E2 gesehen")).to_be_hidden()
    assert WatchedEpisode.objects.count() == 1
