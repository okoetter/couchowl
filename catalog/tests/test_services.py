"""Search, caching in the database and language fallback."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from catalog import services, tmdb
from catalog.models import Title, TitleTranslation
from conftest import load_tmdb_fixture

# --- Search ------------------------------------------------------------------------------


@pytest.fixture
def search_response(fake_tmdb):
    fake_tmdb.add("/3/search/multi", json=load_tmdb_fixture("search_multi"))
    return fake_tmdb


def test_search_returns_movies_and_shows_but_no_people(search_response):
    results = services.search("dark", "de-DE")

    assert [r.title for r in results] == [
        "Dark",  # exact match first, TMDB has it in 4th place
        "The Dark Knight",
        "Dark Matter – Der Zeitenläufer",
        "Dark Shadows",
        "Dark Winds - Der Wind des Bösen",
        "AEW Dark",
    ]
    knight = results[1]
    assert knight.media_type == "movie"
    assert knight.tmdb_id == 155
    assert knight.year == 2008
    assert knight.poster_path.startswith("/")
    assert knight.media_type_label == "Film"
    dark_matter = results[2]
    assert dark_matter.media_type == "tv"
    assert dark_matter.original_title == "Dark Matter"
    assert dark_matter.media_type_label == "Serie"


def test_search_results_are_cached_per_query_and_language(search_response):
    first = services.search("dark", "de-DE")
    cached = services.search("  DARK ", "de-DE")  # same query after normalizing
    assert len(search_response.requests) == 1
    assert cached == first  # sorted the same way

    services.search("dark", "en-US")
    assert len(search_response.requests) == 2


def result(title, year=None, original=None):
    return services.SearchResult("movie", hash(title), title, original or title, year, "")


def test_exact_matches_first_newest_first():
    results = [
        result("Dune: Part Two", 2024),
        result("Dune", 1984),
        result("Dune", None),  # announced, no date yet
        result("Dune Drifter", 2020),
        result("Dune", 2021),
        result("Frank Herbert's Dune", 2000),
    ]

    sorted_results = services.sort_results(results, "dune")

    assert [(r.title, r.year) for r in sorted_results] == [
        ("Dune", 2021),
        ("Dune", 1984),
        ("Dune", None),
        # the rest keeps TMDB's order
        ("Dune: Part Two", 2024),
        ("Dune Drifter", 2020),
        ("Frank Herbert's Dune", 2000),
    ]


def test_exact_match_ignores_case_accents_and_spaces_and_checks_original_title():
    results = [
        result("Something else", 2020),
        result("Die fabelhafte Welt der Amélie", 2001, original="Le Fabuleux Destin d'Amélie"),
        result("Amélie", 1990),
    ]

    assert services.sort_results(results, "AMELIE")[0].year == 1990
    assert services.sort_results(results, "le fabuleux destin d'amelie")[0].year == 2001


def test_without_exact_match_tmdb_order_stays():
    results = [result("B", 2001), result("A", 2020), result("C", 1990)]

    assert services.sort_results(results, "xyz") == results


@pytest.mark.parametrize("query", ["", " ", "x"])
def test_too_short_queries_do_not_ask_tmdb(fake_tmdb, query):
    assert services.search(query, "de-DE") == []
    assert fake_tmdb.requests == []


def test_search_result_without_dates_and_poster():
    result = services.SearchResult.from_tmdb(
        {"media_type": "tv", "id": 1, "name": "Neu", "first_air_date": "", "poster_path": None}
    )

    assert result.year is None
    assert result.poster_path == ""
    assert result.original_title == "Neu"


# --- Language fallback ---------------------------------------------------------------------


def translation(lang, country, **data):
    return {"iso_639_1": lang, "iso_3166_1": country, "data": data}


def details(*translations, original="Original"):
    return {"original_name": original, "translations": {"translations": list(translations)}}


def test_exact_language_wins():
    data = details(
        translation("en", "US", name="English", overview="EN"),
        translation("de", "DE", name="Deutsch", overview="DE"),
        translation("de", "AT", name="Österreichisch", overview="AT"),
    )

    assert services.localize(data, "de-AT", name_field="name") == ("Österreichisch", "AT")


def test_missing_texts_come_from_main_country_of_the_language():
    # This is what TMDB really returns for "Dark" with de-AT: no Austrian description
    data = details(
        translation("de", "CH", name="", overview="CH"),
        translation("de", "DE", name="", overview="DE"),
        translation("de", "AT", name="", overview=""),
        translation("en", "US", name="", overview="EN"),
    )

    assert services.localize(data, "de-AT", name_field="name") == ("Original", "DE")


def test_any_country_of_the_language_before_english():
    data = details(
        translation("en", "US", name="", overview="EN"),
        translation("pt", "PT", name="", overview="PT"),
    )

    assert services.localize(data, "pt-BR", name_field="name") == ("Original", "PT")


def test_english_when_the_language_is_missing():
    data = details(
        translation("en", "GB", name="Attack on Titan (UK)", overview="GB"),
        translation("en", "US", name="Attack on Titan", overview="US"),
        translation("fr", "FR", name="L'Attaque des Titans", overview="FR"),
        original="進撃の巨人",
    )

    assert services.localize(data, "de-DE", name_field="name") == ("Attack on Titan", "US")


def test_original_title_and_empty_description_as_last_resort():
    data = details(translation("fr", "FR", name="Titre", overview="Résumé"))

    assert services.localize(data, "de-DE", name_field="name") == ("Original", "")


def test_movies_use_the_title_field():
    data = {
        "original_title": "Original",
        "translations": {"translations": [translation("de", "DE", title="Titel", overview="")]},
    }

    assert services.localize(data, "de-DE", name_field="title") == ("Titel", "")


# --- Titles in the database ----------------------------------------------------------------


@pytest.fixture
def dark(fake_tmdb):
    fake_tmdb.add_show()
    return fake_tmdb


def details_requests(fake):
    """Requests for the details of a title (shows also send requests for their seasons)."""
    return [r for r in fake.requests if r.url.params["append_to_response"] == "translations"]


@pytest.mark.django_db
def test_get_title_loads_and_stores_with_fallback(dark):
    result = services.get_title("tv", 70523, "de-AT")

    title = result.title
    assert (title.media_type, title.tmdb_id) == ("tv", 70523)
    assert title.original_title == "Dark"
    assert title.release_date == date(2017, 12, 1)
    assert title.status == "Ended"
    assert result.language == "de-AT"
    assert result.name == "Dark"
    # TMDB has no Austrian description; the German one is used
    assert result.overview.startswith("Nach dem Verschwinden eines Kindes")
    assert result.poster_path == "/gw8ZlIXEg6SIx3FgMEQqmBkPYKV.jpg"


@pytest.mark.django_db
def test_movie_is_stored_with_its_release_date(fake_tmdb):
    fake_tmdb.add("/3/movie/155", json=load_tmdb_fixture("movie_155"))

    result = services.get_title("movie", 155, "de-DE")

    assert result.name == "The Dark Knight"
    assert result.title.release_date == date(2008, 7, 16)
    assert result.overview.startswith("Gemeinsam mit Bezirksstaatsanwalt")


@pytest.mark.django_db
def test_fresh_data_comes_from_the_database(dark):
    services.get_title("tv", 70523, "de-AT")
    services.get_title("tv", 70523, "de-AT")

    assert len(details_requests(dark)) == 1


@pytest.mark.django_db
def test_each_language_is_loaded_separately(dark):
    services.get_title("tv", 70523, "de-AT")
    english = services.get_title("tv", 70523, "en-US")

    assert len(details_requests(dark)) == 2
    assert english.overview.startswith("A missing child")
    assert Title.objects.count() == 1
    assert TitleTranslation.objects.count() == 2


@pytest.mark.django_db
def test_outdated_data_is_reloaded(dark):
    stored = services.get_title("tv", 70523, "de-AT")
    TitleTranslation.objects.filter(pk=stored.pk).update(
        fetched_at=timezone.now() - timedelta(hours=25)
    )

    services.get_title("tv", 70523, "de-AT")

    assert len(details_requests(dark)) == 2
    assert TitleTranslation.objects.count() == 1


@pytest.mark.django_db
def test_force_reloads_fresh_data(dark):
    services.get_title("tv", 70523, "de-AT")
    services.get_title("tv", 70523, "de-AT", force=True)

    assert len(details_requests(dark)) == 2


@pytest.mark.django_db
def test_outdated_data_is_used_when_tmdb_is_down(dark):
    stored = services.get_title("tv", 70523, "de-AT")
    TitleTranslation.objects.filter(pk=stored.pk).update(
        fetched_at=timezone.now() - timedelta(days=3)
    )
    dark.add("/3/tv/70523", json={}, status=503)

    result = services.get_title("tv", 70523, "de-AT")

    assert result.pk == stored.pk


@pytest.mark.django_db
def test_errors_without_stored_data_are_raised(fake_tmdb):
    fake_tmdb.add("/3/tv/1", json={}, status=503)
    fake_tmdb.add("/3/tv/2", json={}, status=404)

    with pytest.raises(tmdb.TMDBError):
        services.get_title("tv", 1, "de-DE")
    with pytest.raises(tmdb.TMDBNotFound):
        services.get_title("tv", 2, "de-DE")


# --- Stored translations for lists -----------------------------------------------------------


@pytest.mark.django_db
def test_best_translations_prefers_the_closest_stored_language():
    data = load_tmdb_fixture("movie_155")
    for language in ("fr-FR", "en-US", "de-DE"):
        title = services.save_title("movie", data, language).title
    dark = services.save_title("tv", load_tmdb_fixture("tv_70523"), "fr-FR").title

    best = services.best_translations([title, dark], "de-AT")

    assert best[title.pk].language == "de-DE"
    assert best[dark.pk].language == "fr-FR"  # any language is better than none
    assert services.best_translations([title], "es-ES")[title.pk].language == "en-US"
