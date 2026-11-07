"""Screenshots of important pages for visual review (light/dark, desktop/phone).

Run with: uv run pytest -m e2e e2e/test_screenshots.py
Images are written to screenshots/ (ignored by git).
"""

from pathlib import Path

import pytest

from conftest import load_tmdb_fixture, tiny_png
from e2e.conftest import LOCALE, login

pytestmark = pytest.mark.e2e

OUTPUT = Path(__file__).resolve().parent.parent / "screenshots"
VIEWPORTS = {"desktop": {"width": 1280, "height": 800}, "phone": {"width": 390, "height": 844}}


def show_login_error(page, url):
    login(page, url, "anna", "wrong", expect_success=False)


def show_register(page, url):
    from accounts.models import Invitation

    page.goto(url + Invitation.objects.create(email="ben@example.com").get_absolute_url())
    page.locator("#id_username").fill("ben")
    page.locator("#id_password1").fill("123")
    page.locator("#id_password2").fill("456")
    page.get_by_role("button", name="Konto anlegen").click()
    page.wait_for_load_state()


def show_profile(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/accounts/profile/")
    page.get_by_text("Erweitert").click()
    page.wait_for_timeout(300)  # let Pico's chevron animation finish


def show_password_change(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/accounts/password/change/")
    page.locator("#id_old_password").fill("wrong")
    page.locator("#id_new_password1").fill("Another-long-Pa55word")
    page.locator("#id_new_password2").fill("Another-long-Pa55word")
    page.get_by_role("button", name="Passwort ändern").click()
    page.wait_for_load_state()


def show_search(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/search/")
    page.get_by_placeholder("Film oder Serie").press_sequentially("dark")
    page.locator(".search-results img").first.wait_for()
    page.wait_for_load_state("networkidle")  # all poster thumbnails loaded


def show_search_error(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/search/?q=fail")


PAGES = {
    "login-error": show_login_error,
    "register-error": show_register,
    "profile": show_profile,
    "password-change-error": show_password_change,
    "search": show_search,
    "search-error": show_search_error,
}


def fake_search(fake_tmdb):
    """Search results for "dark" with colored placeholder posters."""
    data = load_tmdb_fixture("search_multi")
    fake_tmdb.add("/3/search/multi", json=data)
    colors = [(26, 43, 74), (120, 40, 40), (40, 100, 60), (90, 70, 20), (60, 60, 60), (30, 90, 110)]
    for item, color in zip(data["results"], colors * 2, strict=False):
        if item.get("poster_path"):
            for size in ("w92", "w185"):
                fake_tmdb.add(
                    f"/t/p/{size}{item['poster_path']}",
                    content=tiny_png(color),
                    headers={"Content-Type": "image/png"},
                )


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("device", VIEWPORTS)
@pytest.mark.parametrize("name", PAGES)
def test_screenshot(live_server, member, browser, fake_tmdb, name, device, scheme):
    fake_search(fake_tmdb)
    if name == "search-error":
        fake_tmdb.add("/3/search/multi", json={}, status=503)
    context = browser.new_context(locale=LOCALE, viewport=VIEWPORTS[device], color_scheme=scheme)
    page = context.new_page()

    PAGES[name](page, live_server.url)

    OUTPUT.mkdir(exist_ok=True)
    page.screenshot(path=OUTPUT / f"{name}-{device}-{scheme}.png", full_page=True)
    context.close()
