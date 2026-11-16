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
    # Away from the button: on hover it shows the next episode ("S1 E3") instead
    page.mouse.move(0, 0)
    expect(page.get_by_text("2/26")).to_be_visible()
    page.get_by_role("button", name="Rückgängig").click()
    expect(page.get_by_text("1/26")).to_be_visible()
    expect(page.get_by_text("S1 E2 gesehen")).to_be_hidden()
    assert WatchedEpisode.objects.count() == 1


@pytest.mark.parametrize(
    "viewport", [{"width": 1280, "height": 800}, {"width": 390, "height": 844}]
)
def test_next_episode_link_scrolls_the_episode_into_view(
    live_server, member, browser, fake_tmdb, viewport
):
    """The sticky top bar (desktop) must not cover the episode the link jumps to."""
    from catalog import services, shows
    from catalog.models import Episode
    from e2e.conftest import LOCALE

    fake_tmdb.add_show()
    for size in ("w92", "w185", "w342", "w500"):
        fake_tmdb.add_image(size, "gw8ZlIXEg6SIx3FgMEQqmBkPYKV.jpg")
    show = services.get_title("tv", 70523, "de-DE").title
    for number in (1, 2):
        shows.mark_episode(
            member, Episode.objects.get(season__show=show, season__number=1, number=number)
        )
    context = browser.new_context(locale=LOCALE, viewport=viewport)
    page = context.new_page()
    login(page, live_server.url, "anna")
    page.goto(f"{live_server.url}/tv/70523/")

    page.get_by_role("link", name="S1 E3").click()
    page.wait_for_url("**#episode-1-3")
    page.wait_for_load_state("networkidle")

    episode = page.locator("#episode-1-3").bounding_box()
    nav = page.locator(".app-nav").bounding_box()
    nav_bottom = nav["y"] + nav["height"] if nav["y"] < 100 else 0  # phones: bar at the bottom
    assert episode["y"] >= nav_bottom
    assert episode["y"] + episode["height"] <= viewport["height"]
    context.close()


def test_jumped_to_episode_lights_up_on_every_click(live_server, member, page, fake_tmdb):
    """A second click on the same link doesn't change the URL; the highlight must restart."""
    fake_tmdb.add_show()
    for size in ("w92", "w185", "w342", "w500"):
        fake_tmdb.add_image(size, "gw8ZlIXEg6SIx3FgMEQqmBkPYKV.jpg")
    login(page, live_server.url, "anna")
    page.goto(f"{live_server.url}/tv/70523/")
    episode = page.locator("#episode-1-1")
    running = "el => el.getAnimations().length"

    page.get_by_role("link", name="S1 E1").click()
    page.wait_for_url("**#episode-1-1")
    assert episode.evaluate(running) == 1
    page.wait_for_timeout(2700)  # the highlight is over
    assert episode.evaluate(running) == 0

    page.mouse.wheel(0, -2000)
    page.get_by_role("link", name="S1 E1").click()
    assert episode.evaluate(running) == 1


def test_mark_earlier_episodes_too(live_server, member, page, fake_tmdb):
    """Marking S2 E3 asks about the 12 episodes before it; "All" marks them, "Undo" takes
    them back, S2 E3 stays."""
    fake_tmdb.add_show()
    for size in ("w92", "w185", "w342", "w500"):
        fake_tmdb.add_image(size, "gw8ZlIXEg6SIx3FgMEQqmBkPYKV.jpg")
    url = live_server.url
    login(page, url, "anna")
    page.goto(f"{url}/tv/70523/?season=2")

    page.get_by_role("button", name="S2 E3 als gesehen markieren").click()
    toast = page.locator(".toast")
    expect(toast).to_contain_text("S2 E3 gesehen. Davor sind noch 12 Folgen offen.")
    # No timeout: still there after the undo messages would have gone
    page.wait_for_timeout(6500)
    expect(toast).to_be_visible()

    toast.get_by_role("button", name="Alle (12)").click()
    expect(page.get_by_text("12 Folgen gesehen.")).to_be_visible()
    expect(page.get_by_text("13 von 26 Folgen gesehen")).to_be_visible()
    expect(page.get_by_role("button", name="S2 E1 als nicht gesehen markieren")).to_be_visible()
    expect(page.locator("#season-1-info")).to_contain_text("Gesehen")
    # Season 1 was closed: its episodes are there when opened, with "date unknown"
    page.get_by_text("Staffel 1", exact=True).click()
    expect(page.locator("#episode-1-10")).to_contain_text("Datum unbekannt")

    page.get_by_role("button", name="Rückgängig").click()
    expect(page.get_by_text("1 von 26 Folgen gesehen")).to_be_visible()
    expect(page.get_by_role("button", name="S2 E1 als gesehen markieren")).to_be_visible()
    assert WatchedEpisode.objects.count() == 1


def test_no_closes_the_question(live_server, member, page, fake_tmdb):
    fake_tmdb.add_show()
    for size in ("w92", "w185", "w342", "w500"):
        fake_tmdb.add_image(size, "gw8ZlIXEg6SIx3FgMEQqmBkPYKV.jpg")
    login(page, live_server.url, "anna")
    page.goto(f"{live_server.url}/tv/70523/")

    page.get_by_role("button", name="S1 E3 als gesehen markieren").click()
    page.get_by_role("button", name="Nein").click()

    expect(page.locator(".toast")).to_have_count(0)
    assert WatchedEpisode.objects.count() == 1


def test_mark_the_whole_show_as_not_watched(live_server, member, page, fake_tmdb):
    """From the list (completely watched) and from the show page, after confirming."""
    from catalog import lists as list_rules
    from catalog import services, shows

    fake_tmdb.add_show()
    for size in ("w92", "w185", "w342", "w500"):
        fake_tmdb.add_image(size, "gw8ZlIXEg6SIx3FgMEQqmBkPYKV.jpg")
    show = services.get_title("tv", 70523, "de-DE").title
    watchlist = member.lists.create(name="Watchlist")
    list_rules.add_to_list(watchlist, show)
    for season in show.seasons.all():
        shows.mark_season(member, season)
    url = live_server.url
    login(page, url, "anna")
    dialogs = []
    answer = {"accept": False}

    def on_dialog(dialog):
        dialogs.append(dialog.message)
        dialog.accept() if answer["accept"] else dialog.dismiss()

    page.on("dialog", on_dialog)

    # List: dismissing the question changes nothing
    page.goto(url + watchlist.get_absolute_url())
    button = page.get_by_role("button", name="„Dark“ als nicht gesehen markieren")
    button.click()
    expect(button).to_be_visible()
    assert dialogs == ["Alle Folgen von „Dark“ als nicht gesehen markieren?"]
    assert WatchedEpisode.objects.exists()

    answer["accept"] = True
    button.click()
    page.mouse.move(0, 0)  # on hover the button shows the next episode instead
    expect(page.get_by_text("0/26")).to_be_visible()
    assert not WatchedEpisode.objects.exists()

    # Show page: seasons and progress line follow without a reload
    shows.mark_season(member, show.seasons.get(number=1))
    page.goto(f"{url}/tv/70523/")
    expect(page.locator("#season-1-info")).to_contain_text("Gesehen")
    page.get_by_role("button", name="Alle als nicht gesehen markieren").click()
    expect(page.get_by_text("0 von 26 Folgen gesehen")).to_be_visible()
    assert dialogs[-1] == "Alle Folgen dieser Serie als nicht gesehen markieren?"
    expect(page.locator("#season-1-info")).not_to_contain_text("Gesehen")
    expect(page.get_by_role("button", name="Alle als nicht gesehen markieren")).to_have_count(0)
    assert not WatchedEpisode.objects.exists()
