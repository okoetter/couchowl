"""Loading data from TMDB: search, caching in the database and language fallback."""

import hashlib
import logging
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from . import tmdb
from .models import MediaType, Title, TitleTranslation

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 100


# --- Search --------------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    media_type: str
    tmdb_id: int
    title: str
    original_title: str
    year: int | None
    poster_path: str

    @property
    def media_type_label(self) -> str:
        return MediaType(self.media_type).label

    @classmethod
    def from_tmdb(cls, item: dict) -> SearchResult:
        is_movie = item["media_type"] == MediaType.MOVIE
        title = item.get("title" if is_movie else "name") or ""
        original = item.get("original_title" if is_movie else "original_name") or title
        released = _parse_date(item.get("release_date" if is_movie else "first_air_date"))
        return cls(
            media_type=item["media_type"],
            tmdb_id=item["id"],
            title=title or original,
            original_title=original,
            year=released.year if released else None,
            poster_path=item.get("poster_path") or "",
        )


def normalize_query(query: str) -> str:
    """Collapse whitespace and cut overly long input."""
    return " ".join(query.split())[:MAX_QUERY_LENGTH]


def search(query: str, language: str) -> list[SearchResult]:
    """Movies and shows matching `query`, with texts in `language`.

    Results are cached for TMDB_SEARCH_CACHE_SECONDS, so typing the same query again
    (or another user searching for it) costs no TMDB request.
    """
    query = normalize_query(query)
    if len(query) < MIN_QUERY_LENGTH:
        return []

    digest = hashlib.sha256(f"{language}|{query.casefold()}".encode()).hexdigest()
    cache_key = f"tmdb:search:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        results = [SearchResult(**item) for item in cached]
    else:
        data = tmdb.get_client().search(query, language)
        results = [
            SearchResult.from_tmdb(item)
            for item in data.get("results", [])
            # /search/multi also finds people; watchit only lists movies and shows
            if item.get("media_type") in MediaType.values
        ]
        # Plain dicts in TMDB's order, so cached entries survive code changes here
        cache.set(cache_key, [asdict(r) for r in results], settings.TMDB_SEARCH_CACHE_SECONDS)
    return sort_results(results, query)


def sort_results(results: list[SearchResult], query: str) -> list[SearchResult]:
    """Exact title matches first, newest first among them; the rest in TMDB's order.

    TMDB sorts by relevance, which strongly favours popular titles, so an exact match
    ("Dark") can end up behind better-known partial matches ("The Dark Knight").
    Among exact matches (remakes, new editions) the most recent one usually is wanted.
    Exact matches without a year come after the dated ones.
    """
    wanted = _comparable(query)

    def key(result: SearchResult) -> tuple[int, int]:
        if wanted in (_comparable(result.title), _comparable(result.original_title)):
            return (0, -(result.year or 0))
        return (1, 0)  # sorted() keeps the original order for equal keys

    return sorted(results, key=key)


def _comparable(text: str) -> str:
    """Ignore case, accents and extra spaces: 'Amélie ' == 'amelie'."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(without_accents.casefold().split())


# --- Titles --------------------------------------------------------------------------------


def get_title(
    media_type: str, tmdb_id: int, language: str, *, force: bool = False
) -> TitleTranslation:
    """A movie or show in `language`, loaded from TMDB if missing or outdated.

    Data older than TMDB_MAX_AGE is refreshed; `force=True` always refreshes
    ("refresh now" button). If TMDB is unreachable, outdated data is better than none.
    Raises tmdb.TMDBNotFound if the title does not exist, tmdb.TMDBError if it can't be loaded.
    """
    translation = (
        TitleTranslation.objects.select_related("title")
        .filter(title__media_type=media_type, title__tmdb_id=tmdb_id, language=language)
        .first()
    )
    if translation and not force and not is_outdated(translation):
        return translation

    try:
        data = tmdb.get_client().details(media_type, tmdb_id, language)
    except tmdb.TMDBNotFound:
        raise
    except tmdb.TMDBError:
        if translation is None:
            raise
        logger.warning("Showing outdated data for %s %s: TMDB unavailable", media_type, tmdb_id)
        return translation

    return save_title(media_type, data, language)


def is_outdated(translation: TitleTranslation) -> bool:
    return translation.fetched_at < timezone.now() - settings.TMDB_MAX_AGE


@transaction.atomic
def save_title(media_type: str, data: dict, language: str) -> TitleTranslation:
    """Store a TMDB details response (with translations) for `language`."""
    is_movie = media_type == MediaType.MOVIE
    original = data.get("original_title" if is_movie else "original_name") or ""
    title, _created = Title.objects.update_or_create(
        media_type=media_type,
        tmdb_id=data["id"],
        defaults={
            "original_title": original,
            "original_language": data.get("original_language") or "",
            "release_date": _parse_date(data.get("release_date" if is_movie else "first_air_date")),
            "status": data.get("status") or "",
        },
    )
    name, overview = localize(data, language, name_field="title" if is_movie else "name")
    translation, _created = TitleTranslation.objects.update_or_create(
        title=title,
        language=language,
        defaults={
            "name": name or original,
            "overview": overview,
            "poster_path": data.get("poster_path") or "",
            "fetched_at": timezone.now(),
        },
    )
    return translation


def localize(data: dict, language: str, *, name_field: str) -> tuple[str, str]:
    """Name and description in `language`, filled from related languages if missing.

    Order: exact language (de-AT) > same language, main country (de-DE) > same language,
    any country > English (en-US, then any) > original title / empty description.
    TMDB leaves a translated name empty when it equals the original title.
    """
    translations = data.get("translations", {}).get("translations", [])
    ranked = sorted(
        (
            (rank, t.get("data") or {})
            for t in translations
            if (rank := _language_rank(t, language)) is not None
        ),
        key=lambda pair: pair[0],
    )
    name = next((d[name_field] for _rank, d in ranked if d.get(name_field)), "")
    overview = next((d["overview"] for _rank, d in ranked if d.get("overview")), "")
    original = data.get("original_title" if name_field == "title" else "original_name") or ""
    return name or original, overview


def _language_rank(translation: dict, language: str) -> int | None:
    """Lower is better; None = don't use this translation."""
    wanted_language, _sep, wanted_country = language.partition("-")
    lang, country = translation.get("iso_639_1"), translation.get("iso_3166_1")
    if lang == wanted_language:
        if country == wanted_country:
            return 0
        if country == wanted_language.upper():  # de-DE, fr-FR, …
            return 1
        return 2
    if lang == "en":
        return 3 if country == "US" else 4
    return None


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None
