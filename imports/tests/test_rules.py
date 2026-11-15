from datetime import date

import httpx
import pytest
from django.utils import timezone

from catalog import lists as list_rules
from catalog import services, shows
from catalog.models import Episode, Title, UserSeries, WatchedEpisode, WatchedMovie
from conftest import dark_seasons, load_tmdb_fixture
from imports import rules
from imports.models import Import, ImportLine
from imports.rules import LineState

from .conftest import movie, tv

Status = ImportLine.Status


def make_import(user, lines, *, list_name="Watchlist", watched=False, follow=False):
    return rules.create_import(user, lines, list_name=list_name, watched=watched, follow=follow)


def analyze_all(user, batch):
    while batch.state == Import.State.ANALYZING:
        rules.step(user, batch)
    return {line.text: line for line in batch.lines.all()}


def import_all(user, batch):
    rules.start(user, batch)
    batch.refresh_from_db()
    while batch.state == Import.State.IMPORTING:
        rules.step(user, batch)
    return {line.text: line.result for line in batch.lines.all()}


def states(user, batch):
    lines, _summary = rules.preview(user, batch)
    return {line.text: line.state for line in lines}


# --- Searching ---------------------------------------------------------------------------------


def test_single_exact_match_is_matched(searches):
    found = rules.find("The Dark Knight", "de-DE")

    assert found.status == Status.MATCHED
    assert found.match.key == "movie-155"


def test_exact_match_ignores_other_results(searches):
    searches["dark"].append(movie(600, "Dark Water", 2005))
    del searches["dark"][2]  # only one exact "Dark" left

    found = rules.find("Dark", "de-DE")

    assert found.status == Status.MATCHED
    assert found.match.key == "tv-70523"


def test_several_exact_matches_are_ambiguous(searches):
    found = rules.find("Dark", "de-DE")

    assert found.status == Status.AMBIGUOUS
    assert found.match is None
    # Exact matches first, newest first
    assert [c.key for c in found.candidates] == ["tv-70523", "movie-500", "movie-155"]


def test_year_picks_the_match(searches):
    found = rules.find("Dark (2005)", "de-DE")

    assert found.status == Status.MATCHED
    assert found.match.key == "movie-500"


def test_original_title_matches(searches):
    searches["dark"] = [tv(70523, "Dark – Die Serie", 2017, original="Dark")]

    assert rules.find("Dark", "de-DE").match.key == "tv-70523"


def test_year_one_off_is_ambiguous_with_the_closest_on_top(searches):
    found = rules.find("Dark (2016)", "de-DE")

    assert found.status == Status.AMBIGUOUS
    assert found.candidates[0].key == "tv-70523"


def test_trailing_number_is_part_of_the_title_when_the_year_finds_nothing(searches):
    searches["wonder woman"] = [movie(297762, "Wonder Woman", 2017)]
    searches["wonder woman 1984"] = [movie(464052, "Wonder Woman 1984", 2020)]

    found = rules.find("Wonder Woman 1984", "de-DE")

    assert found.status == Status.MATCHED
    assert found.match.key == "movie-464052"


def test_trailing_year_matches(searches):
    found = rules.find("Dark 2017", "de-DE")

    assert found.match.key == "tv-70523"


def test_wrong_trailing_year_prefers_exact_titles(searches):
    """ "Dark 2016": nothing exact either way; "Dark" (2017) is offered first."""
    searches["dark 2016"] = [movie(700, "Darkness 2016", 2016)]

    found = rules.find("Dark 2016", "de-DE")

    assert found.status == Status.AMBIGUOUS
    assert found.candidates[0].key == "tv-70523"


def test_no_exact_match_is_ambiguous(searches):
    searches["dark kni"] = [movie(155, "The Dark Knight", 2008)]

    found = rules.find("Dark Kni", "de-DE")

    assert found.status == Status.AMBIGUOUS
    assert [c.key for c in found.candidates] == ["movie-155"]


def test_nothing_found(searches):
    assert rules.find("Gibt es nicht", "de-DE").status == Status.NOT_FOUND


def test_at_most_five_candidates(searches):
    searches["dark"] = [movie(i, "Dark", 2000 + i) for i in range(1, 9)]

    assert len(rules.find("Dark", "de-DE").candidates) == rules.MAX_CANDIDATES


# --- Analysis in chunks ------------------------------------------------------------------------


def test_analysis_runs_in_chunks(user, searches, monkeypatch):
    monkeypatch.setattr(rules, "CHUNK_SIZE", 2)
    batch = make_import(user, ["The Dark Knight", "Dark", "Nope"])

    first = rules.step(user, batch)

    assert (first.done, first.total) == (2, 3)
    assert batch.state == Import.State.ANALYZING
    rules.step(user, batch)
    batch.refresh_from_db()
    assert batch.state == Import.State.PREVIEW
    lines = {line.text: line for line in batch.lines.all()}
    assert lines["The Dark Knight"].status == Status.MATCHED
    assert lines["The Dark Knight"].choice == "movie-155"
    assert lines["Dark"].status == Status.AMBIGUOUS
    assert lines["Dark"].choice == ""
    assert lines["Nope"].status == Status.NOT_FOUND


def test_tmdb_error_keeps_the_line_pending(user, searches, fake_tmdb):
    batch = make_import(user, ["The Dark Knight"])
    fake_tmdb.add("/3/search/multi", json={}, status=503)

    with pytest.raises(services.tmdb.TMDBError):
        rules.step(user, batch)

    line = batch.lines.get()
    assert line.status == Status.PENDING
    assert line.claimed_at is None


def test_claimed_lines_are_left_to_the_other_request(user, searches, fake_tmdb):
    batch = make_import(user, ["The Dark Knight", "Dark"])
    batch.lines.update(claimed_at=timezone.now())

    progress = rules.step(user, batch)

    assert progress.done == 0
    assert progress.waiting
    assert not fake_tmdb.requests


def test_abandoned_claims_are_taken_over(user, searches):
    batch = make_import(user, ["The Dark Knight"])
    batch.lines.update(claimed_at=timezone.now() - rules.CLAIM_TIMEOUT * 2)

    assert rules.step(user, batch).done == 1


# --- Preview -------------------------------------------------------------------------------------


@pytest.fixture
def stored_movie(db):
    return services.save_title("movie", load_tmdb_fixture("movie_155"), "de-DE").title


@pytest.fixture
def stored_show(db):
    data = load_tmdb_fixture("tv_70523")
    return services.save_title("tv", data, "de-DE", seasons=dark_seasons("de-DE")).title


def test_preview_states_problem_lines_first(user, searches):
    batch = make_import(user, ["The Dark Knight", "Nope", "Dark", "The Dark Knight"])
    analyze_all(user, batch)

    lines, summary = rules.preview(user, batch)

    assert [(line.text, line.state) for line in lines] == [
        ("Dark", LineState.CHOOSE),
        ("Nope", LineState.NOT_FOUND),
        ("The Dark Knight", LineState.IMPORT),
        ("The Dark Knight", LineState.DUPLICATE),
    ]
    assert lines[3].duplicate_of.number == 1
    assert (summary.to_import, summary.choose, summary.not_found, summary.skipped) == (1, 1, 1, 1)


def test_already_on_the_list(user, searches, stored_movie):
    list_rules.add_to_list(user.lists.create(name="Watchlist"), stored_movie)
    batch = make_import(user, ["The Dark Knight"], list_name="watchlist")
    analyze_all(user, batch)

    assert states(user, batch) == {"The Dark Knight": LineState.EXISTING}


def test_on_the_list_but_not_watched_is_imported(user, searches, stored_movie):
    """Importing a watch history into the watchlist still marks titles on it."""
    list_rules.add_to_list(user.lists.create(name="Watchlist"), stored_movie)
    batch = make_import(user, ["The Dark Knight"], watched=True)
    analyze_all(user, batch)

    assert states(user, batch) == {"The Dark Knight": LineState.IMPORT}
    list_rules.mark_watched(user, stored_movie)
    assert states(user, batch) == {"The Dark Knight": LineState.EXISTING}


def test_already_there_without_list(user, searches, stored_show):
    batch = make_import(user, ["Dark (2017)"], list_name="", follow=True)
    analyze_all(user, batch)

    assert states(user, batch) == {"Dark (2017)": LineState.IMPORT}
    shows.set_following(user, stored_show, True)
    assert states(user, batch) == {"Dark (2017)": LineState.EXISTING}


def test_choice_and_skip(user, searches):
    batch = make_import(user, ["Dark"])
    line = analyze_all(user, batch)["Dark"]

    rules.set_choice(line, "movie-500")
    assert states(user, batch) == {"Dark": LineState.IMPORT}
    rules.set_choice(line, "movie-999")  # not a candidate: ignored
    assert line.choice == "movie-500"
    rules.set_choice(line, ImportLine.SKIP)
    assert states(user, batch) == {"Dark": LineState.SKIP}


def test_search_again(user, searches):
    batch = make_import(user, ["Dark Knigth"])
    line = analyze_all(user, batch)["Dark Knigth"]
    assert line.status == Status.NOT_FOUND

    rules.search_again(line, "  The Dark Knight ", "de-DE")

    line.refresh_from_db()
    assert line.query == "The Dark Knight"
    assert line.text == "Dark Knigth"
    assert line.choice == "movie-155"


# --- Import --------------------------------------------------------------------------------------


def test_import_adds_to_a_new_list_and_marks_watched(user, searches):
    batch = make_import(user, ["The Dark Knight", "Dark (2017)"], list_name="Seen", watched=True)
    analyze_all(user, batch)

    results = import_all(user, batch)

    assert results == {"The Dark Knight": "imported", "Dark (2017)": "imported"}
    seen = user.lists.get(name="Seen")
    assert {item.title.tmdb_id for item in seen.items.all()} == {155, 70523}
    assert WatchedMovie.objects.get(user=user).watched_at is None
    dark = Title.objects.get(tmdb_id=70523)
    assert shows.progress(user, [dark])[dark.pk].complete
    # Specials don't count and aren't marked
    assert not WatchedEpisode.objects.filter(user=user, episode__season__number=0).exists()
    assert set(WatchedEpisode.objects.filter(user=user).values_list("watched_at", flat=True)) == {
        None
    }
    batch.refresh_from_db()
    assert batch.state == Import.State.DONE


def test_watched_show_without_follow_is_not_followed(user, searches):
    batch = make_import(user, ["Dark (2017)"], list_name="", watched=True)
    analyze_all(user, batch)

    import_all(user, batch)

    series = UserSeries.objects.get(user=user)
    assert not series.following
    assert series.status == UserSeries.Status.WATCHING
    # Marking another episode later doesn't follow it either (status is set)
    episode = Episode.objects.filter(season__show=series.title, season__number=0).first()
    episode.air_date = date(2020, 1, 1)
    episode.save()
    shows.mark_episode(user, episode)
    assert not shows.is_following(user, series.title)


def test_follow_also_follows_unfollowed_shows(user, searches, stored_show):
    shows.mark_episode(user, Episode.objects.filter(season__number=1).first())
    shows.set_following(user, stored_show, False)
    batch = make_import(user, ["Dark (2017)"], list_name="", follow=True)
    analyze_all(user, batch)

    assert import_all(user, batch) == {"Dark (2017)": "imported"}
    assert shows.is_following(user, stored_show)
    # Not marked as watched: the line wasn't
    assert WatchedEpisode.objects.filter(user=user).count() == 1


def test_follow_is_decided_per_line(user, searches, fake_tmdb):
    """The form's checkbox is only the default; each show line has its own switch."""
    data = load_tmdb_fixture("tv_70523") | {"id": 2883, "name": "Dark Shadows"}
    fake_tmdb.add_show(data)
    searches["dark shadows"] = [tv(2883, "Dark Shadows", 1966)]
    batch = make_import(user, ["Dark (2017)", "Dark Shadows"], list_name="", follow=True)
    lines = analyze_all(user, batch)
    assert lines["Dark (2017)"].follow
    rules.set_follow(lines["Dark Shadows"], False)
    rules.set_watched(lines["Dark Shadows"], True)

    import_all(user, batch)

    followed = {s.title.tmdb_id for s in UserSeries.objects.filter(user=user, following=True)}
    assert followed == {70523}
    # Watched, but not followed: the line's switch decides, not the first mark
    assert UserSeries.objects.get(user=user, title__tmdb_id=2883).status == "watching"


def test_follow_only_on_a_line_is_not_already_there(user, searches, stored_show):
    batch = make_import(user, ["Dark (2017)"], list_name="", watched=True)
    line = analyze_all(user, batch)["Dark (2017)"]
    shows.mark_show_watched(user, stored_show, follow=False)
    assert states(user, batch) == {"Dark (2017)": LineState.EXISTING}

    rules.set_follow(line, True)

    assert states(user, batch) == {"Dark (2017)": LineState.IMPORT}


def test_duplicates_are_merged_follow_wins(user, searches):
    batch = make_import(user, ["Dark (2017)", "Dark 2017"], list_name="", watched=True)
    lines = analyze_all(user, batch)
    rules.set_follow(lines["Dark 2017"], True)

    import_all(user, batch)

    assert UserSeries.objects.get(user=user).following


def test_existing_dates_are_kept(user, searches, stored_movie, stored_show):
    list_rules.mark_watched(user, stored_movie, date(2020, 5, 1))
    first = Episode.objects.get(season__show=stored_show, season__number=1, number=1)
    shows.mark_episode(user, first, date(2021, 3, 4))
    batch = make_import(user, ["The Dark Knight", "Dark (2017)"], watched=True)
    analyze_all(user, batch)

    import_all(user, batch)

    assert WatchedMovie.objects.get(user=user).watched_at == date(2020, 5, 1)
    assert WatchedEpisode.objects.get(user=user, episode=first).watched_at == date(2021, 3, 4)


def test_skipped_missing_and_duplicate_lines(user, searches, fake_tmdb, stored_movie):
    list_rules.add_to_list(user.lists.create(name="Watchlist"), stored_movie)
    batch = make_import(user, ["The Dark Knight", "Dark", "Nope", "Dark (2005)", "Dark 2005"])
    analyze_all(user, batch)
    fake_tmdb.add("/3/movie/500", json=load_tmdb_fixture("movie_155") | {"id": 500})

    results = import_all(user, batch)

    assert results == {
        "The Dark Knight": "existing",  # already on the list
        "Dark": "missing",  # no choice
        "Nope": "missing",
        "Dark (2005)": "imported",
        "Dark 2005": "duplicate",  # same title as the line before
    }
    result = rules.result(batch)
    assert result.imported == 1
    assert [(line.text, line.title_url) for line in result.skipped] == [
        ("The Dark Knight", "/movie/155/"),
        ("Dark 2005", "/movie/500/"),
    ]
    assert result.skipped[1].duplicate_of.text == "Dark (2005)"
    assert result.missing_text == "Dark\nNope"


def test_duplicates_are_merged_watched_wins(user, searches):
    batch = make_import(user, ["The Dark Knight", "The Dark Knight (2008)"], list_name="")
    lines = analyze_all(user, batch)
    rules.set_watched(lines["The Dark Knight (2008)"], True)

    results = import_all(user, batch)

    assert results == {"The Dark Knight": "imported", "The Dark Knight (2008)": "duplicate"}
    assert WatchedMovie.objects.filter(user=user).exists()


def test_title_gone_from_tmdb_is_not_imported(user, searches, fake_tmdb):
    batch = make_import(user, ["The Dark Knight"])
    analyze_all(user, batch)
    fake_tmdb.add("/3/movie/155", json={}, status=404)

    assert import_all(user, batch) == {"The Dark Knight": "missing"}


def test_tmdb_error_stops_the_import_and_keeps_the_line(user, searches, fake_tmdb):
    batch = make_import(user, ["The Dark Knight"])
    analyze_all(user, batch)
    rules.start(user, batch)
    batch.refresh_from_db()
    fake_tmdb.add("/3/movie/155", json=lambda request: httpx.Response(503))

    with pytest.raises(services.tmdb.TMDBError):
        rules.step(user, batch)

    line = batch.lines.get()
    assert line.result == ""
    assert line.claimed_at is None
    assert not user.lists.get(name="Watchlist").items.exists()


def test_create_import_twice_returns_the_first(user):
    first = make_import(user, ["Dark"])

    assert make_import(user, ["Heat"]) == first
    assert list(first.lines.values_list("text", flat=True)) == ["Dark"]
