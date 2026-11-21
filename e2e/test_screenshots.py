"""Screenshots of important pages for visual review (light/dark, desktop/phone).

Run with: uv run pytest -m e2e e2e/test_screenshots.py
Images are written to screenshots/ (ignored by git).
"""

from pathlib import Path

import pytest

from conftest import dark_seasons, load_tmdb_fixture, tiny_png
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


def show_reset_data(page, url):
    """ "Reset my data" after a wrong password: what will be lost, with the error."""
    login(page, url, "anna")
    page.goto(f"{url}/accounts/profile/")
    page.get_by_role("button", name="Meine Daten zurücksetzen …").click()
    page.locator("#id_password").fill("wrong")
    page.get_by_role("button", name="Meine Daten löschen").click()
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


def show_list_grid_hover_show(page, url):
    """Hovering a started show's check (the next episode is named below the title)."""
    show_list_grid(page, url)
    page.get_by_role("button", name="S2 E3 von „Dark“ als gesehen markieren").hover()
    page.wait_for_timeout(300)


def show_list_compact(page, url):
    show_list_grid(page, url)
    page.get_by_role("button", name="Kompakte Liste").click()
    page.locator(".compact-list").wait_for()
    page.wait_for_load_state("networkidle")


def show_list_grid_edit(page, url):
    show_list_grid(page, url)
    page.get_by_role("button", name="Bearbeiten").click()


def show_list_compact_edit(page, url):
    show_list_compact(page, url)
    page.get_by_role("button", name="Bearbeiten").click()


def show_list_remove_toast(page, url):
    show_list_grid_edit(page, url)
    page.get_by_role("button", name="„Heat“ von der Liste entfernen").click()
    page.locator(".toast").wait_for()


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


def show_movie_poster(page, url):
    """The poster enlarged (click on it)."""
    login(page, url, "anna")
    page.goto(f"{url}/movie/155/")
    page.get_by_role("link", name="Poster vergrößern").click()
    page.locator("dialog img[src*='/w780/']").wait_for()
    page.wait_for_load_state("networkidle")


def show_movie_many_offers(page, url):
    """Many providers (like "Dunkirk"): the logos wrap, groups must stay apart.
    No free offers: a group without providers is left out."""
    from catalog.models import Title

    logos = sorted(
        {
            p["logo_path"]
            for name in ("movie_155", "tv_70523")
            for offers in load_tmdb_fixture(name)["watch/providers"]["results"].values()
            for kind, providers in offers.items()
            if kind != "link"
            for p in providers
        }
    )

    def providers(count, start):
        return [
            {"id": start + i, "name": f"Provider {start + i}", "logo": logos[i % len(logos)]}
            for i in range(count)
        ]

    title = Title.objects.get(tmdb_id=155, media_type="movie")
    title.watch_providers["DE"] = {
        "flatrate": providers(5, 100),
        "rent": providers(8, 200),
        "buy": providers(9, 300),
    }
    title.save(update_fields=["watch_providers"])
    show_movie(page, url)


def show_show(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/tv/70523/")
    page.wait_for_load_state("networkidle")


def show_movie_cinema(page, url):
    """Not out yet, no offers: cinema and digital release instead (providers.availability)."""
    from datetime import timedelta

    from django.utils import timezone

    from catalog.models import Title

    cinema = timezone.localdate() + timedelta(days=30)
    Title.objects.filter(tmdb_id=155, media_type="movie").update(
        status="Post Production",
        watch_providers={"DE": {}},
        release_dates={
            "DE": {"theatrical": str(cinema), "digital": str(cinema + timedelta(days=60))}
        },
    )
    show_movie(page, url)


def show_show_starts(page, url):
    """A show that starts soon, no offers yet: start date and network instead."""
    from datetime import timedelta

    from django.utils import timezone

    from catalog.models import Title

    Title.objects.filter(tmdb_id=70523, media_type="tv").update(
        status="Planned",
        release_date=timezone.localdate() + timedelta(days=4),
        networks=["Prime Video"],
        watch_providers={"DE": {}},
    )
    show_show(page, url)


def show_show_long_title(page, url):
    """A long title with a long word must wrap instead of widening the page on phones."""
    from catalog.models import TitleTranslation

    TitleTranslation.objects.filter(title__tmdb_id=70523).update(
        name="The Terminal List - Die Abschussliste"
    )
    show_show(page, url)


def show_show_details(page, url):
    """An episode description and a date form opened, season 1 loaded on demand."""
    show_show(page, url)
    page.get_by_text("Anfänge und Enden").click()
    page.locator("#episode-2-1 .episode-watched > summary").click()
    page.get_by_text("Staffel 1", exact=True).click()
    page.locator("#episode-1-1").wait_for()
    page.wait_for_timeout(300)


def show_show_jump(page, url):
    """ "Next: S2 E3" jumps to the episode, which lights up briefly."""
    show_show(page, url)
    page.get_by_role("link", name="S2 E3").click()
    page.wait_for_url("**#episode-2-3")
    page.wait_for_timeout(300)


def show_show_earlier(page, url):
    """ "Mark earlier episodes too?" after marking S3 E2 (gaps in seasons 2 and 3)."""
    login(page, url, "anna")
    page.goto(f"{url}/tv/70523/?season=3")
    page.get_by_role("button", name="S3 E2 als gesehen markieren").click()
    page.locator(".toast-prompt").wait_for()


def show_list_toast(page, url):
    show_list_grid(page, url)
    page.get_by_role("button", name="S2 E3 von „Dark“ als gesehen markieren").click()
    page.locator(".toast").wait_for()


def show_followed(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/lists/followed/")
    page.wait_for_load_state("networkidle")


def show_hover(show, locator):
    """`show` with the mouse over `locator` (phones have no hover: nothing changes)."""

    def run(page, url):
        show(page, url)
        # force: the mouse may rest on an element covered by a link (dashboard cards)
        locator(page).hover(force=True)
        page.wait_for_timeout(300)  # let the transition finish

    return run


def show_dashboard(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/")
    page.wait_for_load_state("networkidle")


def show_dashboard_toast(page, url):
    show_dashboard(page, url)
    page.get_by_role("button", name="S2 E3 von „Dark“ als gesehen markieren").click()
    page.locator(".toast").wait_for()


def show_upcoming(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/upcoming/")
    page.wait_for_load_state("networkidle")


def show_upcoming_busy(page, url):
    """ "Refresh all" shows a spinner while TMDB is asked."""
    show_upcoming(page, url)
    # Keep the page: cancel the form submission after couchowl.js has handled it
    # (window listeners run after the document listener)
    page.evaluate("window.addEventListener('submit', (event) => event.preventDefault())")
    page.get_by_role("button", name="Alle aktualisieren").click()
    page.wait_for_selector("button[aria-busy='true']")


def show_about(page, url):
    login(page, url, "anna")
    page.goto(f"{url}/about/")
    page.wait_for_load_state("networkidle")


def show_about_public(page, url):
    """Logged out, with legal links configured (footer and "Legal" section)."""
    from django.test import override_settings

    with override_settings(
        IMPRINT_URL="https://example.com/impressum", PRIVACY_URL="https://example.com/datenschutz"
    ):
        page.goto(f"{url}/about/")
        page.wait_for_load_state("networkidle")


def show_dashboard_empty(page, url):
    from accounts.models import User
    from e2e.conftest import PASSWORD

    User.objects.create_user(username="ben", password=PASSWORD)
    login(page, url, "ben")
    page.goto(f"{url}/")


IMPORT_LINES = [
    "Dark",
    "Darkk Matter",
    "The Dark Knight",
    "Heat (1995)",
    "Dark Winds",
    "Dark Shadows",
    "Dark Shadows 1966",
]


def sample_import(state):
    """An import of anna's with IMPORT_LINES, searched (see import_search) and in `state`."""
    from accounts.models import User
    from imports import rules
    from imports.models import Import, ImportLine

    user = User.objects.get(username="anna")
    batch = rules.create_import(
        user, IMPORT_LINES, list_name="Watchlist", watched=True, follow=False
    )
    if state == Import.State.ANALYZING:
        # Three lines searched; another tab "works" on the rest, so the bar stays
        rules.CHUNK_SIZE, size = 3, rules.CHUNK_SIZE
        rules.step(user, batch)
        rules.CHUNK_SIZE = size
        batch.lines.filter(status=ImportLine.Status.PENDING).update(claimed_at=timezone_now())
        return
    while batch.state == Import.State.ANALYZING:
        rules.step(user, batch)
    if state == Import.State.DONE:
        results = ["missing", "missing", "existing"] + ["imported"] * 3 + ["duplicate"]
        for line, result in zip(batch.lines.all(), results, strict=True):
            line.result = result
            line.save()
        batch.state = state
        batch.save()


def timezone_now():
    from django.utils import timezone

    return timezone.now()


def show_import(page, url):
    """The paste form with "New list" chosen (shows the name field)."""
    login(page, url, "anna")
    page.goto(f"{url}/import/")
    page.locator("#id_lines").fill("\n".join(IMPORT_LINES))
    page.locator("#id_target").select_option(label="Neue Liste …")
    page.locator("#id_new_list").fill("Gesehen")


def show_import_progress(page, url):
    from imports.models import Import

    sample_import(Import.State.ANALYZING)
    login(page, url, "anna")
    page.goto(f"{url}/import/")
    page.locator("progress").wait_for()


def show_import_preview(page, url):
    from imports.models import Import

    sample_import(Import.State.PREVIEW)
    login(page, url, "anna")
    page.goto(f"{url}/import/")
    page.wait_for_load_state("networkidle")


def show_import_change(page, url):
    """A matched line with "Change" opened, and its watched switch turned off."""
    show_import_preview(page, url)
    line = page.locator(".import-line", has_text="Dark Winds")
    line.get_by_role("switch", name="Gesehen").click()
    page.wait_for_load_state("networkidle")
    line.get_by_text("Ändern").click()
    page.wait_for_load_state("networkidle")


def show_import_result(page, url):
    from imports.models import Import

    sample_import(Import.State.DONE)
    login(page, url, "anna")
    page.goto(f"{url}/import/")
    page.get_by_text("2 übersprungen").click()  # the collapsed list of skipped lines
    page.wait_for_timeout(300)  # let Pico's chevron animation finish


PAGES = {
    "login-error": show_login_error,
    "register-error": show_register,
    "profile": show_profile,
    "password-change-error": show_password_change,
    "reset-data-error": show_reset_data,
    "search": show_search,
    "search-error": show_search_error,
    "search-menu": show_search_menu,
    "lists": show_lists,
    "list-grid": show_list_grid,
    "list-grid-hover": show_list_grid_hover,
    "list-grid-hover-watched": show_list_grid_hover_watched,
    "list-grid-hover-show": show_list_grid_hover_show,
    "list-compact": show_list_compact,
    "list-grid-edit": show_list_grid_edit,
    "list-compact-edit": show_list_compact_edit,
    "list-remove-toast": show_list_remove_toast,
    "list-filtered": show_list_filtered,
    # "Dark" completely watched (see watch_dark): the check mark undoes the whole show
    "list-grid-complete": show_list_grid,
    "list-compact-complete": show_list_compact,
    "movie": show_movie,
    "movie-poster": show_movie_poster,
    "movie-many-offers": show_movie_many_offers,
    "movie-cinema": show_movie_cinema,
    "show": show_show,
    "show-starts": show_show_starts,
    "show-long-title": show_show_long_title,
    "show-details": show_show_details,
    "show-jump": show_show_jump,
    "show-earlier": show_show_earlier,
    "show-complete": show_show,
    # Hover effects: tinted rows, poster frame, bold text link
    "lists-hover": show_hover(show_lists, lambda p: p.get_by_role("link", name="Watchlist")),
    "search-hover": show_hover(show_search, lambda p: p.locator(".result-link").nth(1)),
    "list-grid-hover-poster": show_hover(
        show_list_grid, lambda p: p.locator(".poster-grid a").nth(1)
    ),
    "show-hover-episode": show_hover(
        show_show, lambda p: p.locator(".episodes li:has(details) .episode-meta").first
    ),
    "dashboard-hover": show_hover(
        show_dashboard, lambda p: p.locator(".watching-list progress").first
    ),
    "upcoming-hover": show_hover(show_upcoming, lambda p: p.locator(".result-link").first),
    "about-hover": show_hover(show_about, lambda p: p.get_by_role("link", name="JustWatch")),
    "list-toast": show_list_toast,
    "followed": show_followed,
    "dashboard": show_dashboard,
    "dashboard-toast": show_dashboard_toast,
    "dashboard-empty": show_dashboard_empty,
    "upcoming": show_upcoming,
    "upcoming-busy": show_upcoming_busy,
    "about": show_about,
    "about-public": show_about_public,
    "import": show_import,
    "import-progress": show_import_progress,
    "import-preview": show_import_preview,
    "import-change": show_import_change,
    "import-result": show_import_result,
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


def import_search(fake_tmdb):
    """Search results per query for IMPORT_LINES: "Dark" is ambiguous (show and movie),
    "Darkk Matter" finds nothing, the rest one title each."""
    data = load_tmdb_fixture("search_multi")
    by_id = {item["id"]: item for item in data["results"]}
    dark_movie = {
        "media_type": "movie",
        "id": 500,
        "title": "Dark",
        "original_title": "Dark",
        "release_date": "2005-03-10",
        "poster_path": by_id[196322]["poster_path"],
        "vote_average": 5.1,
        "vote_count": 120,
    }
    heat = {
        "media_type": "movie",
        "id": 158,
        "title": "Heat",
        "original_title": "Heat",
        "release_date": "1995-12-15",
        "poster_path": None,
    }
    results = {
        "dark": [by_id[155], by_id[70523], dark_movie, by_id[196322]],
        "the dark knight": [by_id[155]],
        "heat": [heat],
        "dark winds": [by_id[128904]],
        "dark shadows": [by_id[2883]],
    }
    fake_tmdb.add(
        "/3/search/multi",
        json=lambda request: {"results": results.get(request.url.params["query"].lower(), [])},
    )


def sample_lists(fake_tmdb, user):
    """Two lists with a few titles (variants of the fixtures), one movie watched."""
    from datetime import date

    from catalog import lists as list_rules
    from catalog import services, shows

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
    dark = services.save_title("tv", show, "de-DE", seasons=dark_seasons("de-DE")).title
    titles.append(dark)
    fake_tmdb.add_show(show)
    # Season 1 and two episodes of season 2 watched, the last episode not aired yet
    shows.mark_season(user, dark.seasons.get(number=1), date(2024, 1, 20))
    for number in (1, 2):
        shows.mark_episode(user, dark.seasons.get(number=2).episodes.get(number=number))
    dark.seasons.get(number=3).episodes.filter(number=8).update(air_date=date(2099, 1, 1))
    shows.set_following(user, dark, True)
    for title in titles:
        list_rules.add_to_list(watchlist, title)
    list_rules.mark_watched(user, titles[0], date(2024, 3, 15))
    list_rules.mark_watched(user, titles[2])
    for index, color in zip([0, 1, 2, 9], colors, strict=False):
        for size in ("w92", "w185", "w342", "w500", "w780"):
            fake_tmdb.add(
                f"/t/p/{size}/sample{index}.jpg",
                content=tiny_png(color),
                headers={"Content-Type": "image/png"},
            )


def watch_dark(user):
    """All aired episodes of "Dark" watched."""
    from catalog import shows
    from catalog.models import Title

    for season in Title.objects.get(tmdb_id=70523).seasons.all():
        shows.mark_season(user, season)


def sample_dashboard(fake_tmdb, user):
    """More shows for the dashboard: one being watched, one waiting for its next episode,
    two with announced seasons."""
    from datetime import timedelta

    from django.utils import timezone

    from catalog import services, shows
    from catalog.models import Episode, Season

    def save_show(tmdb_id, name, networks, poster):
        data = load_tmdb_fixture("tv_70523")
        data.update(
            id=tmdb_id,
            original_name=name,
            poster_path=f"/{poster}.jpg",
            networks=[{"id": i, "name": n} for i, n in enumerate(networks)],
        )
        for translation in data["translations"]["translations"]:
            translation["data"]["name"] = ""  # use the original name
        return services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title

    def starts_in(show, number, days):
        start = timezone.localdate() + timedelta(days=days)
        Season.objects.filter(show=show, number=number).update(air_date=start)
        Episode.objects.filter(season__show=show, season__number=number).update(air_date=start)

    long_title = "Ein sehr langer Serientitel, der kaum in eine Zeile passt"
    long_name = save_show(1001, long_title, [], "show1")
    for number in (1, 2, 3):
        shows.mark_episode(user, long_name.seasons.get(number=1).episodes.get(number=number))
    soon = save_show(1002, "Kommt bald", ["ZDF"], "show2")
    starts_in(soon, 3, 1)
    later = save_show(1003, "Später", ["Netflix", "ZDFneo"], "show3")
    starts_in(later, 2, 40)
    for show in (soon, later):
        shows.set_following(user, show, True)
    # Caught up, season 3 is running: waits for E5 in 4 days (date instead of the button)
    waiting = save_show(1004, "Läuft gerade", ["Netflix"], "show2")
    for episode in Episode.objects.filter(season__show=waiting, season__number=3):
        episode.air_date = timezone.localdate() + timedelta(days=7 * (episode.number - 4) - 3)
        episode.save()
    shows.mark_episodes(
        user,
        list(
            Episode.objects.filter(
                season__show=waiting, season__number__gt=0, air_date__lte=timezone.localdate()
            )
        ),
    )
    colors = [(120, 40, 40), (40, 100, 60), (90, 70, 20)]
    for index, color in enumerate(colors, start=1):
        for size in ("w92", "w185"):
            fake_tmdb.add(
                f"/t/p/{size}/show{index}.jpg",
                content=tiny_png(color),
                headers={"Content-Type": "image/png"},
            )


def provider_logos(fake_tmdb):
    """Colored placeholders for the streaming provider logos in the fixtures."""
    colors = [(200, 30, 40), (20, 120, 200), (30, 30, 30), (240, 180, 0), (90, 40, 140)]
    logos = set()
    for name in ("movie_155", "tv_70523"):
        for offers in load_tmdb_fixture(name)["watch/providers"]["results"].values():
            for kind, providers in offers.items():
                if kind != "link":
                    logos.update(p["logo_path"] for p in providers)
    for index, logo in enumerate(sorted(logos)):
        fake_tmdb.add(
            f"/t/p/w92{logo}",
            content=tiny_png(colors[index % len(colors)]),
            headers={"Content-Type": "image/png"},
        )


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("device", VIEWPORTS)
@pytest.mark.parametrize("name", PAGES)
def test_screenshot(live_server, member, browser, fake_tmdb, name, device, scheme):
    fake_search(fake_tmdb)
    sample_lists(fake_tmdb, member)
    if name.endswith("-complete"):
        watch_dark(member)
    if name.startswith(("dashboard", "upcoming")):
        sample_dashboard(fake_tmdb, member)
    provider_logos(fake_tmdb)
    if name.startswith("import"):
        import_search(fake_tmdb)
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
    # Finish running CSS transitions (e.g. a button morphed from the grid to the list)
    page.screenshot(
        path=OUTPUT / f"{name}-{device}-{scheme}.png", full_page=True, animations="disabled"
    )
    context.close()
