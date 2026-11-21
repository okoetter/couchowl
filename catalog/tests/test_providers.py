"""Streaming providers: storing them per region, grouping and the detail page."""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog import providers, services
from catalog.models import MediaType, Title
from catalog.providers import Availability
from conftest import load_tmdb_fixture


def provider(provider_id, name, priority=0, logo="/logo.png"):
    return {
        "provider_id": provider_id,
        "provider_name": name,
        "display_priority": priority,
        "logo_path": logo,
    }


# --- Storing -----------------------------------------------------------------------------------


def test_only_regions_of_users_and_the_default_are_stored(db, settings):
    settings.DEFAULT_REGION = "DE"
    User.objects.create_user(username="anna", region="at")
    User.objects.create_user(username="ben", region="")  # not detected yet: default region

    title = services.save_title("tv", load_tmdb_fixture("tv_70523"), "de-DE").title

    # TMDB sends DE, AT and US; nobody uses US
    assert set(title.watch_providers) == {"AT", "DE"}


def test_providers_are_sorted_by_priority(db):
    title = services.save_title("tv", load_tmdb_fixture("tv_70523"), "de-DE").title

    stored = title.watch_providers["DE"]
    assert [p["name"] for p in stored["flatrate"]] == ["Netflix", "Netflix Standard with Ads"]
    assert stored["flatrate"][0] == {
        "id": 8,
        "name": "Netflix",
        "logo": "/rK1KljqmbvO9HQa1PBFLILWah72.png",
    }


def test_region_without_offers_is_stored_as_empty(db, settings):
    settings.DEFAULT_REGION = "FR"

    title = services.save_title("tv", load_tmdb_fixture("tv_70523"), "de-DE").title

    assert title.watch_providers == {"FR": {}}


def test_missing_logo_and_provider_data(db):
    data = load_tmdb_fixture("tv_70523")
    data["watch/providers"] = {
        "results": {"DE": {"free": [provider(1, "ARD", logo=None), {"provider_id": 2}]}}
    }

    title = services.save_title("tv", data, "de-DE").title

    assert title.watch_providers["DE"] == {"free": [{"id": 1, "name": "ARD", "logo": ""}]}


def test_changed_region_reloads_the_title(fake_tmdb, user):
    fake_tmdb.add_show()
    services.get_title("tv", 70523, "de-DE", region="DE")
    loaded = len(fake_tmdb.requests)

    services.get_title("tv", 70523, "de-DE", region="DE")
    assert len(fake_tmdb.requests) == loaded  # fresh: from the database

    user.region = "AT"
    user.save()
    translation = services.get_title("tv", 70523, "de-DE", region="AT")

    assert len(fake_tmdb.requests) > loaded
    assert "AT" in translation.title.watch_providers


# --- Display -----------------------------------------------------------------------------------


@pytest.fixture
def movie_with_offers(db):
    return services.save_title("movie", load_tmdb_fixture("movie_155"), "de-DE").title


def test_offers_are_grouped_in_order(movie_with_offers):
    groups = providers.offers(movie_with_offers, "DE")

    assert [str(g.label) for g in groups] == ["Abo", "Kostenlos", "Leihen", "Kaufen"]
    assert [p["name"] for p in groups[0].providers] == [
        "Amazon Prime Video",
        "Amazon Prime Video with Ads",
    ]
    assert [p["name"] for p in groups[1].providers] == ["Pluto TV"]


def test_free_and_ads_are_one_group_without_duplicates(db):
    title = Title(
        watch_providers={
            "DE": {"free": [{"id": 1, "name": "ARD", "logo": ""}], "ads": [{"id": 1}, {"id": 2}]}
        }
    )

    [free] = providers.offers(title, "DE")

    assert [p["id"] for p in free.providers] == [1, 2]


def test_no_offers_for_unknown_region(movie_with_offers):
    assert providers.offers(movie_with_offers, "FR") == []


@pytest.mark.parametrize(
    ("networks", "streaming", "expected"),
    [
        (["Netflix"], ["Netflix", "Netflix Standard with Ads"], ["Netflix"]),
        (["ZDF"], ["ZDFneo", "Netflix"], ["ZDF", "ZDFneo", "Netflix"]),
        ([], ["Amazon Prime Video", "Amazon Prime Video with Ads"], ["Amazon Prime Video"]),
        (["HBO"], [], ["HBO"]),
    ],
)
def test_sources_combine_networks_and_streaming(networks, streaming, expected):
    offers = [{"id": i, "name": name, "logo": ""} for i, name in enumerate(streaming)]
    title = Title(networks=networks, watch_providers={"DE": {"flatrate": offers}})

    assert providers.sources(title, "DE") == expected


def test_sources_leave_out_rent_and_buy(movie_with_offers):
    assert providers.sources(movie_with_offers, "DE") == ["Amazon Prime Video", "Pluto TV"]


# --- Detail page -------------------------------------------------------------------------------


def test_detail_page_shows_offers_of_the_users_region(auth_client, movie_with_offers):
    content = auth_client.get(movie_with_offers.get_absolute_url()).content.decode()

    assert "Verfügbar in Deutschland" in content
    assert 'alt="Amazon Prime Video"' in content
    assert "/posters/w92/gMZdpavHmxFNnLpMHwVxfqeux2g.png" in content
    assert "Daten von TMDB und JustWatch, Stand" in content
    assert "/watch?locale=" not in content  # no link to TMDB's offers page
    assert "HBO Max" not in content  # US only


def test_detail_page_without_offers(auth_client, user, fake_tmdb):
    data = load_tmdb_fixture("movie_155")
    del data["watch/providers"]
    fake_tmdb.add("/3/movie/155", json=data)

    content = auth_client.get(reverse("catalog:title_detail", args=["movie", 155])).content
    content = content.decode()

    assert "Keine Streaming-Angebote in Deutschland bekannt." in content


# --- Release dates (movies) --------------------------------------------------------------------


def release(release_type, day):
    return {"type": release_type, "release_date": f"{day}T00:00:00.000Z", "note": ""}


def test_release_dates_per_region(db, settings):
    settings.DEFAULT_REGION = "DE"
    User.objects.create_user(username="anna", region="AT")
    User.objects.create_user(username="ben", region="CH")
    data = load_tmdb_fixture("movie_155")
    data["release_dates"] = {
        "results": [
            # Premiere (1) is ignored; theatrical (3) wins over limited (2)
            {
                "iso_3166_1": "DE",
                "release_dates": [
                    release(1, "2027-02-01"),
                    release(2, "2027-03-01"),
                    release(3, "2027-03-12"),
                    release(4, "2027-06-01"),
                    release(4, "2027-05-28"),
                ],
            },
            {"iso_3166_1": "AT", "release_dates": [release(2, "2027-03-05")]},
            {"iso_3166_1": "US", "release_dates": [release(3, "2027-03-01")]},
        ]
    }

    title = services.save_title("movie", data, "de-DE").title

    assert title.release_dates == {
        "AT": {"theatrical": "2027-03-05"},
        "CH": {},  # no dates known there
        "DE": {"theatrical": "2027-03-12", "digital": "2027-05-28"},
    }


def test_shows_have_no_release_dates(db):
    title = services.save_title("tv", load_tmdb_fixture("tv_70523"), "de-DE").title

    assert title.release_dates == {}


# --- Availability without offers ---------------------------------------------------------------

TODAY = date(2026, 11, 21)
LATER = date(2026, 11, 25)
MUCH_LATER = date(2027, 3, 12)
EARLIER = date(2026, 1, 1)


def a_show(**fields):
    return Title(media_type=MediaType.TV, **{"status": "Planned", **fields})


def a_movie(**fields):
    return Title(media_type=MediaType.MOVIE, **{"status": "Post Production", **fields})


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        pytest.param(
            a_show(release_date=LATER, networks=["Prime Video"]),
            Availability("show_starts", starts=LATER, networks="Prime Video"),
            id="show-starts",
        ),
        pytest.param(
            a_show(networks=["HBO", "Max"]),
            Availability("show_no_date", networks="HBO, Max"),
            id="show-without-date",
        ),
        pytest.param(
            a_show(release_date=EARLIER, networks=["HBO"], status="Returning Series"),
            Availability("none", networks="HBO"),
            id="show-running",
        ),
        pytest.param(
            a_show(status="Ended"),  # out, even if TMDB has no date
            Availability("none"),
            id="show-ended-without-date",
        ),
        pytest.param(
            a_movie(
                release_date=EARLIER,
                release_dates={"DE": {"theatrical": str(MUCH_LATER), "digital": "2027-05-28"}},
            ),
            Availability("cinema", theatrical=MUCH_LATER, digital=date(2027, 5, 28)),
            id="movie-cinema-and-digital",
        ),
        pytest.param(
            a_movie(release_dates={"DE": {"theatrical": str(LATER), "digital": str(EARLIER)}}),
            Availability("cinema", theatrical=LATER),
            id="movie-cinema-digital-already-out",
        ),
        pytest.param(
            a_movie(release_dates={"DE": {"theatrical": str(EARLIER), "digital": str(LATER)}}),
            Availability("digital", digital=LATER),
            id="movie-digital-after-cinema",
        ),
        pytest.param(
            a_movie(release_date=LATER, release_dates={"DE": {}}),
            Availability("release", starts=LATER),
            id="movie-elsewhere",
        ),
        pytest.param(a_movie(), Availability("no_date"), id="movie-without-date"),
        pytest.param(
            a_movie(release_dates={"DE": {"theatrical": str(EARLIER)}}, status="Released"),
            Availability("none"),
            id="movie-out",
        ),
        pytest.param(
            a_movie(release_date=LATER, release_dates={"DE": {"theatrical": str(EARLIER)}}),
            Availability("none"),
            id="movie-out-here-before-elsewhere",
        ),
    ],
)
def test_availability(title, expected):
    assert providers.availability(title, "DE", TODAY) == expected


def test_detail_page_names_start_and_network_of_a_new_show(auth_client, show):
    start = timezone.localdate() + timedelta(days=4)
    Title.objects.filter(pk=show.pk).update(
        release_date=start, status="Planned", networks=["Prime Video"], watch_providers={"DE": {}}
    )

    content = auth_client.get(show.get_absolute_url()).content.decode()

    assert (
        f"Startet am {start:%d.%m.%Y} bei Prime Video. "
        "Angebote für Deutschland folgen meist zum Start."
    ) in " ".join(content.split())
    assert "Originalausstrahlung" not in content


def test_detail_page_names_the_original_broadcaster(auth_client, show):
    Title.objects.filter(pk=show.pk).update(watch_providers={"DE": {}})  # "Dark" has ended

    content = " ".join(auth_client.get(show.get_absolute_url()).content.decode().split())

    assert (
        "Keine Streaming-Angebote in Deutschland bekannt. Originalausstrahlung: Netflix."
    ) in content


def test_detail_page_names_cinema_and_digital_release(auth_client, movie):
    cinema = timezone.localdate() + timedelta(days=30)
    digital = cinema + timedelta(days=60)
    Title.objects.filter(pk=movie.pk).update(
        status="Post Production",
        watch_providers={"DE": {}},
        release_dates={"DE": {"theatrical": str(cinema), "digital": str(digital)}},
    )

    content = " ".join(auth_client.get(movie.get_absolute_url()).content.decode().split())

    assert (
        f"Kinostart in Deutschland am {cinema:%d.%m.%Y}, digital ab {digital:%d.%m.%Y}. "
        "Streaming-Angebote folgen meist nach dem Kinostart."
    ) in content
