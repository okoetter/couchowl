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


def show_search_menu(page, url):
    show_search(page, url)
    page.get_by_role("button", name="„The Dark Knight“ zu einer Liste hinzufügen").click()
    page.get_by_label("Watchlist").wait_for()


def show_lists(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/lists/")


def show_list_grid(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/lists/")
    page.get_by_role("link", name="Watchlist").click()
    page.wait_for_load_state("networkidle")


def show_list_grid_hover(page, url):
    show_list_grid(page, url)
    page.get_by_role("button", name="„Heat“ als gesehen markieren").hover()
    page.wait_for_timeout(300)  # let the transition finish


def show_list_grid_hover_watched(page, url):
    show_list_grid(page, url)
    page.get_by_role("button", name="„Arrival“ als nicht gesehen markieren").hover()
    page.wait_for_timeout(300)


def show_list_compact(page, url):
    show_list_grid(page, url)
    page.get_by_role("button", name="Kompakte Liste").click()
    page.locator(".compact-list").wait_for()
    page.wait_for_load_state("networkidle")


def show_list_filtered(page, url):
    show_list_compact(page, url)
    page.get_by_role("button", name="Ungesehen").click()
    page.wait_for_url("**status=unwatched")
    page.wait_for_load_state("networkidle")


def show_movie(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/movie/155/")
    page.get_by_text("(ändern)").click()
    page.wait_for_load_state("networkidle")


def show_show(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/tv/70523/")
    page.get_by_role("button", name="Zu Liste hinzufügen").click()
    page.wait_for_load_state("networkidle")


PAGES = {
    "login-error": show_login_error,
    "register-error": show_register,
    "profile": show_profile,
    "password-change-error": show_password_change,
    "search": show_search,
    "search-error": show_search_error,
    "search-menu": show_search_menu,
    "lists": show_lists,
    "list-grid": show_list_grid,
    "list-grid-hover": show_list_grid_hover,
    "list-grid-hover-watched": show_list_grid_hover_watched,
    "list-compact": show_list_compact,
    "list-filtered": show_list_filtered,
    "movie": show_movie,
    "show": show_show,
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


def sample_lists(fake_tmdb, user):
    """Two lists with a few titles (variants of the fixtures), one movie watched."""
    from datetime import date

    from catalog import lists as list_rules
    from catalog import services

    colors = [(26, 43, 74), (120, 40, 40), (40, 100, 60), (90, 70, 20), (30, 90, 110)]
    names = ["The Dark Knight", "Ein sehr langer Filmtitel, der umbricht", "Arrival", "Heat"]
    watchlist = user.lists.create(name="Watchlist")
    user.lists.create(name="Mit Familie")
    user.lists.create(name="Animation")
    titles = []
    for index, name in enumerate(names):
        data = load_tmdb_fixture("movie_155")
        data.update(id=155 + index, original_title=name, poster_path=f"/sample{index}.jpg")
        data["release_date"] = f"{2008 + index * 3}-07-16"
        for translation in data["translations"]["translations"]:
            translation["data"]["title"] = ""  # use the original title as name
        if index == 3:
            data["poster_path"] = None
        titles.append(services.save_title("movie", data, "de-DE").title)
    show = load_tmdb_fixture("tv_70523")
    show["poster_path"] = "/sample9.jpg"
    titles.append(services.save_title("tv", show, "de-DE").title)
    fake_tmdb.add("/3/tv/70523", json=show)
    for title in titles:
        list_rules.add_to_list(watchlist, title)
    list_rules.mark_watched(user, titles[0], date(2024, 3, 15))
    list_rules.mark_watched(user, titles[2])
    for index, color in zip([0, 1, 2, 9], colors, strict=False):
        for size in ("w92", "w185", "w342", "w500"):
            fake_tmdb.add(
                f"/t/p/{size}/sample{index}.jpg",
                content=tiny_png(color),
                headers={"Content-Type": "image/png"},
            )


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("device", VIEWPORTS)
@pytest.mark.parametrize("name", PAGES)
def test_screenshot(live_server, member, browser, fake_tmdb, name, device, scheme):
    fake_search(fake_tmdb)
    sample_lists(fake_tmdb, member)
    if name == "search-error":
        fake_tmdb.add("/3/search/multi", json={}, status=503)
    # Phones are touch devices: no hover, so hover-only elements must stay visible there
    touch = {"is_mobile": True, "has_touch": True} if device == "phone" else {}
    context = browser.new_context(
        locale=LOCALE, viewport=VIEWPORTS[device], color_scheme=scheme, **touch
    )
    page = context.new_page()

    PAGES[name](page, live_server.url)

    OUTPUT.mkdir(exist_ok=True)
    page.screenshot(path=OUTPUT / f"{name}-{device}-{scheme}.png", full_page=True)
    context.close()
