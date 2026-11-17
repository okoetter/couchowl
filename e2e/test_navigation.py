"""The bottom tab bar on phones: centered, current page clearly marked."""

import pytest

from e2e.conftest import LOCALE, login

pytestmark = pytest.mark.e2e


@pytest.fixture
def phone(browser):
    context = browser.new_context(
        locale=LOCALE, viewport={"width": 412, "height": 900}, is_mobile=True, has_touch=True
    )
    yield context.new_page()
    context.close()


def test_tab_bar_is_centered(live_server, member, phone):
    login(phone, live_server.url, "anna")
    links = phone.locator(".app-nav ul a")

    first = links.first.bounding_box()
    last = links.last.bounding_box()
    width = phone.viewport_size["width"]
    # Same distance to both screen edges (Pico once shifted the bar to the left)
    assert first["x"] == pytest.approx(width - (last["x"] + last["width"]), abs=1)
    assert first["x"] >= 8  # clear of rounded screen corners


def test_current_page_has_a_tinted_icon(live_server, member, phone):
    login(phone, live_server.url, "anna")
    phone.goto(f"{live_server.url}/search/")

    def icon_background(name):
        icon = phone.locator(".app-nav ul a", has_text=name).locator("svg")
        return icon.evaluate("svg => getComputedStyle(svg).backgroundColor")

    assert icon_background("Dashboard") == "rgba(0, 0, 0, 0)"
    assert icon_background("Suche") != "rgba(0, 0, 0, 0)"
