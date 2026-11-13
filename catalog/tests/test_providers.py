"""Streaming providers: storing them per region, grouping and the detail page."""

import pytest
from django.urls import reverse

from accounts.models import User
from catalog import providers, services
from catalog.models import Title
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


def test_providers_are_sorted_by_priority_and_keep_the_link(db):
    title = services.save_title("tv", load_tmdb_fixture("tv_70523"), "de-DE").title

    stored = title.watch_providers["DE"]
    assert [p["name"] for p in stored["flatrate"]] == ["Netflix", "Netflix Standard with Ads"]
    assert stored["flatrate"][0] == {
        "id": 8,
        "name": "Netflix",
        "logo": "/rK1KljqmbvO9HQa1PBFLILWah72.png",
    }
    assert stored["link"] == "https://www.themoviedb.org/tv/70523-dark/watch?locale=DE"


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
    assert providers.link(movie_with_offers, "FR") == ""


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
    assert "Quelle: JustWatch" in content
    assert "https://www.themoviedb.org/movie/155-the-dark-knight/watch?locale=DE" in content
    assert "HBO Max" not in content  # US only


def test_detail_page_without_offers(auth_client, user, fake_tmdb):
    data = load_tmdb_fixture("movie_155")
    del data["watch/providers"]
    fake_tmdb.add("/3/movie/155", json=data)

    content = auth_client.get(reverse("catalog:title_detail", args=["movie", 155])).content
    content = content.decode()

    assert "Keine Streaming-Angebote in Deutschland bekannt." in content
