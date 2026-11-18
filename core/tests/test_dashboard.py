"""Dashboard page and its "next episode watched" button."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog import services, shows
from catalog.models import Episode, Season, WatchedEpisode
from conftest import dark_seasons, load_tmdb_fixture

HTMX = {"HX-Request": "true"}


@pytest.fixture
def show(db):
    """ "Dark" with its seasons and episodes, stored in German."""
    data = load_tmdb_fixture("tv_70523")
    return services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title


def episode(show, season, number):
    return Episode.objects.select_related("season").get(
        season__show=show, season__number=season, number=number
    )


def watch_all_but_last(user, show):
    """Everything watched except S3 E8."""
    for number in (1, 2):
        shows.mark_season(user, show.seasons.get(number=number))
    shows.mark_episodes(user, list(Episode.objects.filter(season__show=show, season__number=3))[:7])


def watched(user, show):
    return set(
        WatchedEpisode.objects.filter(user=user, episode__season__show=show).values_list(
            "episode__season__number", "episode__number"
        )
    )


def test_empty_dashboard_explains_both_sections(auth_client):
    content = auth_client.get(reverse("core:dashboard")).content.decode()

    assert "Weiterschauen" in content
    assert "erscheinen hier mit ihrer nächsten Folge" in content
    assert "Ankündigungen" in content
    assert "Neue Staffeln gefolgter Serien in den nächsten 3 Monaten" in content
    assert "Folge Serien, um ihre neuen Staffeln hier zu sehen." in content
    assert reverse("imports:page") in content


def test_import_hint_only_while_the_user_has_no_data(auth_client, user):
    """Not for everyone without a show in progress, e.g. not for people with lists."""
    user.lists.create(name="Watchlist")

    content = auth_client.get(reverse("core:dashboard")).content.decode()

    assert "erscheinen hier mit ihrer nächsten Folge" in content
    assert reverse("imports:page") not in content


def test_dashboard_shows_next_episode_and_announcement(auth_client, user, show, fake_tmdb):
    shows.mark_episode(user, episode(show, 1, 1))
    shows.set_following(user, show, True)
    start = timezone.localdate() + timedelta(days=1)
    Season.objects.filter(show=show, number=3).update(air_date=start)
    Episode.objects.filter(season__show=show, season__number=3).update(air_date=start)

    content = auth_client.get(reverse("core:dashboard")).content.decode()

    assert f'id="watching-{show.pk}"' in content
    assert "S1 E2</span> · Lügen" in content
    assert "1 von 18 Folgen gesehen"  # season 3 not aired yet in content
    assert "S1 E2 von „Dark“ als gesehen markieren" in content
    assert "Staffel 3 · Netflix" in content
    assert "morgen" in content
    # Only the database is used, TMDB is never asked
    assert fake_tmdb.requests == []


def test_followed_shows_without_announcements(auth_client, user, show):
    shows.set_following(user, show, True)

    content = auth_client.get(reverse("core:dashboard")).content.decode()

    assert "Keine neuen Staffeln in den nächsten 3 Monaten angekündigt." in content


def test_announcement_months_in_texts(auth_client, user, show, settings):
    settings.ANNOUNCEMENT_MONTHS = 1
    shows.set_following(user, show, True)

    content = auth_client.get(reverse("core:dashboard")).content.decode()

    assert "Neue Staffeln gefolgter Serien im nächsten Monat" in content
    assert "Keine neuen Staffeln im nächsten Monat angekündigt." in content


# --- "Next episode watched" button ---------------------------------------------------------------


def test_check_button_marks_next_episode_and_updates_only_the_entry(auth_client, user, show):
    shows.mark_episode(user, episode(show, 1, 1))

    response = auth_client.post(reverse("core:watch_next", args=[70523]), headers=HTMX)

    assert watched(user, show) == {(1, 1), (1, 2)}
    content = response.content.decode()
    assert content.lstrip().startswith(f'<div class="watching-body" id="watching-body-{show.pk}">')
    assert "<img" not in content  # the poster stays as it is
    assert "S1 E3</span>" in content
    # Message with "undo"
    assert 'hx-swap-oob="innerHTML:#toast"' in content
    assert "S1 E2 gesehen" in content
    assert f'name="undo" value="{episode(show, 1, 2).pk}"' in content
    assert 'hx-target="#watching"' in content


def test_last_episode_removes_the_entry(auth_client, user, show):
    other = services.save_title(
        "tv",
        {**load_tmdb_fixture("tv_70523"), "id": 1, "original_name": "Other"},
        "de-DE",
        seasons=dark_seasons("de-DE"),
    ).title
    shows.mark_episode(user, episode(other, 1, 1))
    watch_all_but_last(user, show)

    response = auth_client.post(reverse("core:watch_next", args=[70523]), headers=HTMX)

    assert response["HX-Retarget"] == "closest li"
    assert response["HX-Reswap"] == "outerHTML"
    assert "S3 E8 gesehen" in response.content.decode()


def test_last_entry_shows_the_empty_section(auth_client, user, show):
    watch_all_but_last(user, show)

    response = auth_client.post(reverse("core:watch_next", args=[70523]), headers=HTMX)

    assert response["HX-Retarget"] == "#watching"
    assert response["HX-Reswap"] == "innerHTML"
    content = response.content.decode()
    assert "erscheinen hier mit ihrer nächsten Folge" in content
    assert "S3 E8 gesehen" in content


def running_season(show):
    """S3 E1-E4 are out, E5 airs in 4 days, then one per week."""
    today = timezone.localdate()
    for ep in Episode.objects.filter(season__show=show, season__number=3):
        ep.air_date = today + timedelta(days=7 * (ep.number - 4) - 3)
        ep.save()


def test_waiting_entry_shows_the_date_instead_of_the_button(auth_client, user, show):
    running_season(show)
    for number in (1, 2):
        shows.mark_season(user, show.seasons.get(number=number))
    shows.mark_episodes(user, list(Episode.objects.filter(season__show=show, season__number=3))[:4])

    content = auth_client.get(reverse("core:dashboard")).content.decode()

    assert f'id="watching-{show.pk}"' in content
    assert "S3 E5</span> · Leben und Tod" in content
    assert "in 4 Tagen" in content
    assert "als gesehen markieren" not in content
    assert reverse("core:watch_next", args=[70523]) not in content


def test_last_aired_episode_turns_the_entry_into_waiting(auth_client, user, show):
    running_season(show)
    for number in (1, 2):
        shows.mark_season(user, show.seasons.get(number=number))
    shows.mark_episodes(user, list(Episode.objects.filter(season__show=show, season__number=3))[:3])

    response = auth_client.post(reverse("core:watch_next", args=[70523]), headers=HTMX)

    content = response.content.decode()
    assert "HX-Retarget" not in response  # the entry stays, only its text part changes
    assert content.lstrip().startswith(f'<div class="watching-body" id="watching-body-{show.pk}">')
    assert "S3 E5</span>" in content
    assert "in 4 Tagen" in content
    assert "S3 E4 gesehen" in content


def test_undo_takes_the_episode_back_and_reloads_the_section(auth_client, user, show):
    shows.mark_episode(user, episode(show, 1, 1))
    second = episode(show, 1, 2)
    shows.mark_episode(user, second)

    response = auth_client.post(
        reverse("core:watch_next", args=[70523]), {"undo": second.pk}, headers=HTMX
    )

    assert watched(user, show) == {(1, 1)}
    content = response.content.decode()
    assert f'id="watching-{show.pk}"' in content
    assert "S1 E2</span>" in content
    # The empty toast hides the message
    assert 'hx-swap-oob="innerHTML:#toast"' in content
    assert "gesehen</span>" not in content


def test_without_javascript_the_button_redirects_with_a_message(auth_client, user, show):
    shows.mark_episode(user, episode(show, 1, 1))

    response = auth_client.post(reverse("core:watch_next", args=[70523]), follow=True)

    assert response.redirect_chain == [(reverse("core:dashboard"), 302)]
    assert "S1 E2 gesehen." in response.content.decode()
    assert watched(user, show) == {(1, 1), (1, 2)}


def test_undo_without_javascript_redirects(auth_client, user, show):
    first = episode(show, 1, 1)
    shows.mark_episode(user, first)

    response = auth_client.post(reverse("core:watch_next", args=[70523]), {"undo": first.pk})

    assert response.status_code == 302
    assert watched(user, show) == set()


def test_undo_only_accepts_episodes_of_this_show(auth_client, user, show, second_show):
    first = episode(second_show, 1, 1)
    shows.mark_episode(user, first)

    response = auth_client.post(reverse("core:watch_next", args=[70523]), {"undo": first.pk})

    assert response.status_code == 404
    assert watched(user, second_show) == {(1, 1)}


@pytest.fixture
def second_show(db):
    data = {**load_tmdb_fixture("tv_70523"), "id": 2, "original_name": "Second"}
    return services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title


def test_unknown_show_is_404(auth_client):
    assert auth_client.post(reverse("core:watch_next", args=[999])).status_code == 404


def test_check_button_needs_post(auth_client, show):
    assert auth_client.get(reverse("core:watch_next", args=[70523])).status_code == 405


def test_dashboard_needs_login(client, db):
    response = client.get(reverse("core:dashboard"))

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("accounts:login"))
