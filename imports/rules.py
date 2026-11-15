"""Batch import: searching the pasted lines, the preview and the import itself.

Views stay thin; the rules live here (see docs/design.md, "Batch import").

Both the search (one TMDB search per line) and the import (loading each title with its
seasons) take too long for one request, so the page asks for one chunk after another
(`step`). Each request claims a line before working on it (`_claim`), so two open tabs
never process the same line.
"""

import time
from dataclasses import asdict, dataclass, field
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from catalog import lists as list_rules
from catalog import services, shows, tmdb
from catalog.models import ListItem, MediaType, Title, UserList, UserSeries, WatchedMovie

from . import parsing
from .models import Import, ImportLine, candidate_key

# A chunk ends after this many lines or seconds, well within gunicorn's 30 s timeout
CHUNK_SIZE = 10
CHUNK_SECONDS = 10
# A claim older than this is considered abandoned (e.g. the worker was restarted)
CLAIM_TIMEOUT = timedelta(minutes=2)
# Candidates shown per line
MAX_CANDIDATES = 5


# --- Creating an import --------------------------------------------------------------------


def create_import(user, lines: list[str], *, list_name: str, watched: bool, follow: bool):
    """Store a new import with its lines (not searched yet). One import per user: if
    there already is one (e.g. the form was sent twice), that one is returned."""
    try:
        with transaction.atomic():
            batch = Import.objects.create(
                user=user, list_name=list_name, watched=watched, follow=follow
            )
            ImportLine.objects.bulk_create(
                ImportLine(
                    batch=batch, position=i, text=text, query=text, watched=watched, follow=follow
                )
                for i, text in enumerate(lines)
            )
    except IntegrityError:
        return Import.objects.get(user=user)
    return batch


# --- Searching -------------------------------------------------------------------------------


@dataclass
class Found:
    status: str
    candidates: list[services.SearchResult]
    match: services.SearchResult | None = None


def find(text: str, language: str) -> Found:
    """Search TMDB for one line. Raises tmdb.TMDBError.

    Matched: exactly one result matches the title exactly (and the year, if given).
    Ambiguous: several exact matches, none, or none with the year; the best candidates
    come first. Not found: no results at all.
    """
    fallback = None
    for attempt in parsing.attempts(text):
        results = services.search(attempt.query, language)
        ranked = _rank(results, attempt)
        matching = [
            r
            for r in ranked
            if services.is_exact_match(r, attempt.query)
            and (attempt.year is None or r.year == attempt.year)
        ]
        if len(matching) == 1:
            return Found(ImportLine.Status.MATCHED, ranked[:MAX_CANDIDATES], matching[0])
        if matching:
            return Found(ImportLine.Status.AMBIGUOUS, ranked[:MAX_CANDIDATES])
        # No match: keep the first attempt with results, preferring exact titles
        # ("Dark 2016": the show "Dark" from 2017 comes before what "Dark 2016" finds)
        has_exact = any(services.is_exact_match(r, attempt.query) for r in results)
        if results and (fallback is None or (has_exact and not fallback[1])):
            fallback = (ranked, has_exact)
    if fallback:
        return Found(ImportLine.Status.AMBIGUOUS, fallback[0][:MAX_CANDIDATES])
    return Found(ImportLine.Status.NOT_FOUND, [])


def _rank(results: list[services.SearchResult], attempt: parsing.Attempt):
    """Exact title matches first, those closest to the wanted year first (search order
    otherwise: newest first); the rest in search order."""

    def key(result):
        if not services.is_exact_match(result, attempt.query):
            return (1, 0)
        if attempt.year is None:
            return (0, 0)
        return (0, abs((result.year or 0) - attempt.year))

    return sorted(results, key=key)  # stable: equal keys keep the search order


def analyze(line: ImportLine, language: str) -> None:
    """Search the line's query and store the outcome; a single match is preselected."""
    _store(line, find(line.query, language))


def _store(line: ImportLine, found: Found) -> None:
    line.status = found.status
    line.candidates = [asdict(c) for c in found.candidates]
    line.choice = found.match.key if found.match else ""
    ImportLine.objects.filter(pk=line.pk).update(
        status=line.status, candidates=line.candidates, choice=line.choice, claimed_at=None
    )


def search_again(line: ImportLine, query: str, language: str) -> None:
    """Preview: search with another text ("Search again"); empty text changes nothing.

    Raises tmdb.TMDBError (the line stays as it was).
    """
    lines = parsing.split_lines(query)
    if not lines:
        return
    found = find(lines[0], language)
    line.query = lines[0]
    ImportLine.objects.filter(pk=line.pk).update(query=line.query)
    _store(line, found)


def set_choice(line: ImportLine, choice: str) -> None:
    """Preview: choose a candidate (by key) or ImportLine.SKIP. Unknown keys are ignored."""
    keys = {candidate_key(c) for c in line.candidates}
    if choice in keys or choice == ImportLine.SKIP:
        line.choice = choice
        line.save(update_fields=["choice"])


def set_watched(line: ImportLine, watched: bool) -> None:
    line.watched = watched
    line.save(update_fields=["watched"])


def set_follow(line: ImportLine, follow: bool) -> None:
    line.follow = follow
    line.save(update_fields=["follow"])


# --- Preview ---------------------------------------------------------------------------------


class LineState:
    """What happens with a line on import (shown in the preview)."""

    CHOOSE = "choose"  # ambiguous, nothing chosen yet: skipped
    NOT_FOUND = "not_found"  # nothing found: skipped
    IMPORT = "import"
    EXISTING = "existing"  # importing would change nothing
    DUPLICATE = "duplicate"  # same title as an earlier line: merged into it
    SKIP = "skip"  # skipped by the user

    # Order in the preview: problem lines first
    ORDER = (CHOOSE, NOT_FOUND, IMPORT, EXISTING, DUPLICATE, SKIP)


@dataclass
class Summary:
    """Counts per LineState for the preview ("3 lines still need a choice")."""

    counts: dict[str, int] = field(default_factory=dict)

    @property
    def to_import(self) -> int:
        return self.counts.get(LineState.IMPORT, 0)

    @property
    def choose(self) -> int:
        return self.counts.get(LineState.CHOOSE, 0)

    @property
    def not_found(self) -> int:
        return self.counts.get(LineState.NOT_FOUND, 0)

    @property
    def skipped(self) -> int:
        """Already there, duplicates and lines skipped by the user."""
        return sum(
            self.counts.get(state, 0)
            for state in (LineState.EXISTING, LineState.DUPLICATE, LineState.SKIP)
        )


def _merge_duplicates(lines) -> dict[int, ImportLine]:
    """Set `duplicate_of` (the earlier line with the same title, or None) and
    `merged_watched` and `merged_follow` (if any line of the title wants it) on every line.

    Returns the first line per title key.
    """
    first: dict[str, ImportLine] = {}
    for line in sorted(lines, key=lambda line: line.position):
        line.duplicate_of = None
        line.merged_watched = line.watched
        line.merged_follow = line.follow
        if line.choice in ("", ImportLine.SKIP):
            continue
        if line.choice in first:
            line.duplicate_of = first[line.choice]
            line.duplicate_of.merged_watched |= line.watched
            line.duplicate_of.merged_follow |= line.follow
        else:
            first[line.choice] = line
    return first


@dataclass
class Existing:
    """What the user already has, for the titles of some lines (by key)."""

    on_list: set[str]
    watched: set[str]
    followed: set[str]


def existing(user, batch: Import, keys) -> Existing:
    """Which of the titles (by key) are on the target list, watched (shows: all aired
    episodes) and followed. Titles that aren't stored yet have nothing."""
    by_type = {MediaType.MOVIE: [], MediaType.TV: []}
    for key in keys:
        media_type, _sep, tmdb_id = key.partition("-")
        if media_type in by_type and tmdb_id.isdigit():
            by_type[media_type].append(int(tmdb_id))
    movies = list(Title.objects.filter(media_type=MediaType.MOVIE, tmdb_id__in=by_type["movie"]))
    tv = list(Title.objects.filter(media_type=MediaType.TV, tmdb_id__in=by_type["tv"]))
    key_of = {title.pk: f"{title.media_type}-{title.tmdb_id}" for title in movies + tv}

    on_list = set()
    target = _target_list(user, batch)
    if target is not None:
        on_list = {
            key_of[pk]
            for pk in ListItem.objects.filter(user_list=target, title__in=movies + tv).values_list(
                "title_id", flat=True
            )
        }
    watched = {
        key_of[pk]
        for pk in WatchedMovie.objects.filter(user=user, title__in=movies).values_list(
            "title_id", flat=True
        )
    }
    watched |= {key_of[pk] for pk, done in shows.progress(user, tv).items() if done.complete}
    followed = {
        key_of[pk]
        for pk in UserSeries.objects.filter(user=user, title__in=tv, following=True).values_list(
            "title_id", flat=True
        )
    }
    return Existing(on_list=on_list, watched=watched, followed=followed)


def _target_list(user, batch: Import) -> UserList | None:
    if not batch.list_name:
        return None
    return user.lists.filter(name__iexact=batch.list_name).first()


def _changes_nothing(batch: Import, line: ImportLine, have: Existing) -> bool:
    """Whether importing the line would change nothing (it is "already there")."""
    key = line.choice
    if batch.list_name and key not in have.on_list:
        return False
    if line.merged_watched and key not in have.watched:
        return False
    return not (line.merged_follow and key.startswith("tv-") and key not in have.followed)


def preview(user, batch: Import, lines=None) -> tuple[list[ImportLine], Summary]:
    """All lines with `state` (see LineState) and `duplicate_of`, problem lines first.

    `lines`: the lines to return (default: all); duplicates are always checked against
    all lines of the import.
    """
    every = list(batch.lines.all())
    _merge_duplicates(every)
    have = existing(user, batch, {line.choice for line in every if line.duplicate_of is None})
    for line in every:
        if line.choice == ImportLine.SKIP:
            line.state = LineState.SKIP
        elif not line.choice:
            line.state = (
                LineState.NOT_FOUND
                if line.status == ImportLine.Status.NOT_FOUND
                else LineState.CHOOSE
            )
        elif line.duplicate_of is not None:
            line.state = LineState.DUPLICATE
        elif _changes_nothing(batch, line, have):
            line.state = LineState.EXISTING
        else:
            line.state = LineState.IMPORT
    summary = Summary()
    for line in every:
        summary.counts[line.state] = summary.counts.get(line.state, 0) + 1
        # For templates: like search results (key, type label, rating)
        line.options = [services.SearchResult(**c) for c in line.candidates]
        line.chosen_option = next((o for o in line.options if o.key == line.choice), None)
        line.group = line.state if line.state in LineState.ORDER[:3] else LineState.SKIP
    if lines is not None:
        wanted = {line.pk for line in lines}
        every = [line for line in every if line.pk in wanted]
    every.sort(key=lambda line: (LineState.ORDER.index(line.state), line.position))
    return every, summary


# --- Processing in chunks --------------------------------------------------------------------


@dataclass
class Progress:
    done: int
    total: int
    # Lines are left, but another tab is working on them: ask again a little later
    waiting: bool = False


def step(user, batch: Import) -> Progress:
    """Search or import the next chunk of lines, then move on to the next state when
    all lines are done. Raises tmdb.TMDBError; the line being processed stays pending."""
    if batch.state == Import.State.ANALYZING:
        pending = Q(status=ImportLine.Status.PENDING)
        work = _analyze_chunk
        next_state = Import.State.PREVIEW
    elif batch.state == Import.State.IMPORTING:
        pending = Q(result="")
        work = _import_chunk
        next_state = Import.State.DONE
    else:
        return progress(batch)
    processed = work(user, batch, pending)
    current = progress(batch)
    if current.done >= current.total:
        # Conditional, so two tabs finishing at once don't both change it
        Import.objects.filter(pk=batch.pk, state=batch.state).update(state=next_state)
        batch.state = next_state
    elif not processed:
        current.waiting = True
    return current


def progress(batch: Import) -> Progress:
    if batch.state in (Import.State.ANALYZING, Import.State.PREVIEW):
        pending = Q(status=ImportLine.Status.PENDING)
    else:
        pending = Q(result="")
    counts = batch.lines.aggregate(total=Count("pk"), pending=Count("pk", filter=pending))
    return Progress(done=counts["total"] - counts["pending"], total=counts["total"])


def _claim(batch: Import, pending: Q) -> ImportLine | None:
    """The next pending line that no other request is working on, marked as taken.

    The update only succeeds if the line is still free ("conditional update"), so two
    requests can't take the same line.
    """
    now = timezone.now()
    free = Q(claimed_at__isnull=True) | Q(claimed_at__lt=now - CLAIM_TIMEOUT)
    for line in batch.lines.filter(pending, free).order_by("position")[:CHUNK_SIZE]:
        if ImportLine.objects.filter(pending, free, pk=line.pk).update(claimed_at=now):
            line.claimed_at = now
            return line
    return None


def _release(line: ImportLine) -> None:
    ImportLine.objects.filter(pk=line.pk).update(claimed_at=None)


def _chunk(batch: Import, pending: Q, work) -> int:
    """Run `work(line)` on claimed lines until the chunk is full; returns how many."""
    started = time.monotonic()
    processed = 0
    while processed < CHUNK_SIZE and time.monotonic() - started < CHUNK_SECONDS:
        line = _claim(batch, pending)
        if line is None:
            break
        try:
            work(line)
        except Exception:
            _release(line)
            raise
        processed += 1
    return processed


def _analyze_chunk(user, batch: Import, pending: Q) -> int:
    language = user.effective_tmdb_language
    return _chunk(batch, pending, lambda line: analyze(line, language))


def _import_chunk(user, batch: Import, pending: Q) -> int:
    lines = list(batch.lines.all())
    _merge_duplicates(lines)
    by_pk = {line.pk: line for line in lines}
    target = list_rules.find_or_create_list(user, batch.list_name) if batch.list_name else None

    def work(claimed):
        line = by_pk[claimed.pk]
        result = import_line(user, batch, line, target)
        ImportLine.objects.filter(pk=line.pk).update(result=result, claimed_at=None)

    return _chunk(batch, pending, work)


def start(user, batch: Import) -> None:
    """Preview → importing. A new target list is created now."""
    if batch.list_name:
        list_rules.find_or_create_list(user, batch.list_name)
    Import.objects.filter(pk=batch.pk, state=Import.State.PREVIEW).update(
        state=Import.State.IMPORTING
    )


def import_line(user, batch: Import, line: ImportLine, target: UserList | None) -> str:
    """Import one line (see _merge_duplicates for `duplicate_of` and the merged switches).

    Nothing existing is changed: list entries stay, watched dates are kept. Returns an
    ImportLine.Result. Raises tmdb.TMDBError when the title can't be loaded.
    """
    if not line.choice:
        return ImportLine.Result.MISSING
    if line.choice == ImportLine.SKIP:
        return ImportLine.Result.SKIPPED
    if line.duplicate_of is not None:
        return ImportLine.Result.DUPLICATE
    if _changes_nothing(batch, line, existing(user, batch, [line.choice])):
        return ImportLine.Result.EXISTING
    media_type, _sep, tmdb_id = line.choice.partition("-")
    try:
        # Loads the title (shows with seasons and episodes) unless it is stored and fresh
        title = services.get_title(
            media_type,
            int(tmdb_id),
            user.effective_tmdb_language,
            region=user.effective_region,
        ).title
    except tmdb.TMDBNotFound:
        return ImportLine.Result.MISSING  # gone from TMDB since the search
    # One transaction per line: never half a line
    with transaction.atomic():
        if target is not None:
            list_rules.add_to_list(target, title)
        if title.is_movie:
            if line.merged_watched:
                WatchedMovie.objects.get_or_create(
                    user=user, title=title, defaults={"watched_at": None}
                )
        elif line.merged_watched:
            shows.mark_show_watched(user, title, follow=line.merged_follow)
        elif line.merged_follow:
            shows.set_following(user, title, True)
    return ImportLine.Result.IMPORTED


# --- Result ----------------------------------------------------------------------------------


_SKIPPED_RESULTS = (
    ImportLine.Result.EXISTING,
    ImportLine.Result.DUPLICATE,
    ImportLine.Result.SKIPPED,
)


@dataclass
class Result:
    imported: int
    # Lines with `duplicate_of` (see _merge_duplicates) and `title_url` (or "")
    skipped: list[ImportLine]
    missing: list[str]  # the lines that weren't imported, as pasted

    @property
    def missing_text(self) -> str:
        return "\n".join(self.missing)


def result(batch: Import) -> Result:
    lines = list(batch.lines.all())
    _merge_duplicates(lines)
    skipped = [line for line in lines if line.result in _SKIPPED_RESULTS]
    for line in skipped:
        media_type, _sep, tmdb_id = line.choice.partition("-")
        line.title_url = (
            reverse("catalog:title_detail", args=[media_type, int(tmdb_id)])
            if media_type in MediaType.values and tmdb_id.isdigit()
            else ""
        )
    return Result(
        imported=sum(1 for line in lines if line.result == ImportLine.Result.IMPORTED),
        skipped=skipped,
        missing=[line.text for line in lines if line.result == ImportLine.Result.MISSING],
    )
