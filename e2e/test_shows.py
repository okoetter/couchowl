"""Shows in a real browser: follow, mark episodes and seasons, progress in lists."""

import pytest
from playwright.sync_api import expect

from catalog.models import TitleTranslation, WatchedEpisode
from conftest import load_tmdb_fixture
from e2e.conftest import LOCALE, login

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
    expect(page.get_by_role("button", name="Gefolgt")).to_be_visible()

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
    # "▶ S1 E3" below the title and the bar on the poster follow
    expect(page.locator(".next-episode")).to_contain_text("S1 E3")
    expect(page.locator(".poster-progress progress")).to_have_attribute("value", "2")
    page.get_by_role("button", name="Rückgängig").click()
    expect(page.locator(".next-episode")).to_contain_text("S1 E2")
    expect(page.locator(".poster-progress progress")).to_have_attribute("value", "1")
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
    expect(page.locator(".next-episode")).to_contain_text("S1 E1")
    expect(page.get_by_role("button", name="S1 E1 von „Dark“ als gesehen markieren")).to_have_count(
        1
    )
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


@pytest.mark.parametrize(
    ("width", "text_size"),
    [(320, "100%"), (360, "100%"), (390, "100%"), (360, "125%"), (412, "125%")],
)
def test_long_title_does_not_widen_the_page_on_phones(
    live_server, member, browser, fake_tmdb, width, text_size
):
    """A long title with long words ("Abschussliste") and the rating with its votes wrap;
    nothing sticks out on the right.

    Pixel widths depend on the system font (wider on the CI runner than on most desktops),
    so the page is also checked with larger text, like Android's font size setting: that
    leaves room for wider fonts (not on 320 px: with 125 % that's like a 256 px screen).
    """
    show = load_tmdb_fixture("tv_70523")
    fake_tmdb.add_show(show | {"poster_path": None, "watch/providers": {"results": {}}})
    context = browser.new_context(
        locale=LOCALE, viewport={"width": width, "height": 800}, is_mobile=True, has_touch=True
    )
    page = context.new_page()
    login(page, live_server.url, "anna")

    page.goto(f"{live_server.url}/tv/70523/")  # loads the show into the database
    TitleTranslation.objects.update(name="The Terminal List - Die Abschussliste")
    page.reload()
    expect(page.locator("h1")).to_have_text("The Terminal List - Die Abschussliste")
    page.add_style_tag(content=f"html {{ font-size: {text_size} !important; }}")

    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow == 0
    context.close()


@pytest.fixture
def watchlist_with_dark(member, fake_tmdb):
    from catalog import lists, services

    fake_tmdb.add_show()
    for size in ("w92", "w185", "w342", "w500"):
        fake_tmdb.add_image(size, "gw8ZlIXEg6SIx3FgMEQqmBkPYKV.jpg")
    watchlist = lists.find_or_create_list(member, "Watchlist")
    lists.add_to_list(watchlist, services.get_title("tv", 70523, "de-DE").title)
    return watchlist


def test_back_button_shows_the_new_follow_state(live_server, page, watchlist_with_dark):
    """Going back must show the bell. Chromium would take the list from its HTTP cache; the
    new version cookie makes it ask the server (Django answers with "Vary: Cookie")."""
    login(page, live_server.url, "anna")
    page.goto(f"{live_server.url}/lists/{watchlist_with_dark.pk}/")
    bell = page.locator('.follow-toggle button[aria-pressed="true"]')
    expect(bell).to_have_count(0)

    page.get_by_role("link", name="Dark").first.click()
    page.get_by_role("button", name="Folgen", exact=True).click()
    expect(page.get_by_role("button", name="Gefolgt")).to_be_visible()
    page.go_back()
    expect(bell.first).to_be_visible()

    page.get_by_role("link", name="Dark").first.click()
    page.get_by_role("button", name="Gefolgt").click()
    expect(page.get_by_role("button", name="Folgen", exact=True)).to_be_visible()
    page.go_back()
    expect(bell).to_have_count(0)


def test_page_from_the_bfcache_updates_in_place(live_server, page, watchlist_with_dark):
    """Real browsers keep the previous page in memory (bfcache) and show it again as it was.

    Headless Chromium has no bfcache, so this does what it would: the list stays as it is,
    the show is followed elsewhere, then the page gets the "pageshow" event.
    """
    login(page, live_server.url, "anna")
    page.goto(f"{live_server.url}/lists/{watchlist_with_dark.pk}/")
    bell = page.locator('.follow-toggle button[aria-pressed="true"]')
    poster = page.locator(".list-content img, #list-content img").first.element_handle()
    restored = "() => dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))"

    # Nothing changed: no request
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    page.evaluate(restored)
    page.wait_for_timeout(500)
    assert requests == []

    other = page.context.new_page()
    other.goto(f"{live_server.url}/tv/70523/")
    other.get_by_role("button", name="Folgen", exact=True).click()
    expect(other.get_by_role("button", name="Gefolgt")).to_be_visible()
    page.evaluate(restored)
    expect(bell.first).to_be_visible()
    # Morphed into place: the poster stays (no flicker)
    assert poster.evaluate("img => img.isConnected")


def test_click_anywhere_in_an_episode_row_opens_its_description(
    live_server, member, page, fake_tmdb
):
    fake_tmdb.add_show()
    login(page, live_server.url, "anna")
    page.goto(f"{live_server.url}/tv/70523/")
    row = page.locator("#episode-1-1")
    details = row.locator("details.episode-info")

    # A click on the air date line, not on the name, opens the description
    row.locator(".episode-meta").click()
    expect(details).to_have_attribute("open", "")
    # A click into the open description keeps it open (its text stays selectable)
    row.locator(".episode-info > p").click()
    expect(details).to_have_attribute("open", "")
    row.locator(".episode-meta").click()
    expect(details).not_to_have_attribute("open", "")

    # The check button only marks the episode
    page.get_by_role("button", name="S1 E1 als gesehen markieren").click()
    expect(page.get_by_role("button", name="S1 E1 als nicht gesehen markieren")).to_be_visible()
    expect(page.locator("#episode-1-1 details.episode-info")).not_to_have_attribute("open", "")


def test_continue_watching_card_opens_the_show_from_anywhere(live_server, member, page, fake_tmdb):
    fake_tmdb.add_show()
    for size in ("w185", "w342", "w500"):
        fake_tmdb.add_image(size, "gw8ZlIXEg6SIx3FgMEQqmBkPYKV.jpg")
    url = live_server.url
    login(page, url, "anna")
    page.goto(f"{url}/tv/70523/")
    page.get_by_role("button", name="Folgen", exact=True).click()
    expect(page.get_by_role("button", name="Gefolgt")).to_be_visible()
    page.get_by_role("button", name="S1 E1 als gesehen markieren").click()
    expect(page.get_by_role("button", name="S1 E1 als nicht gesehen markieren")).to_be_visible()

    # The check button in the card marks the next episode and stays on the dashboard
    page.goto(f"{url}/")
    card = page.locator(".watching-list li").first
    card.get_by_role("button", name="S1 E2 von „Dark“ als gesehen markieren").click()
    expect(page.get_by_text("S1 E2 gesehen")).to_be_visible()
    assert page.url == f"{url}/"

    # A click on the progress bar (not the title) opens the show: the title link lies
    # over the whole card, so the mouse click at the bar's position hits the link
    # (force: Playwright would otherwise wait for the bar to be clickable itself)
    card.locator("progress").click(force=True)
    expect(page).to_have_url(f"{url}/tv/70523/")
