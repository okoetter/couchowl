"""Loading data from TMDB: search, caching in the database and language fallback."""

import hashlib
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from accounts.regions import default_region

from . import tmdb
from .models import (
    Episode,
    EpisodeTranslation,
    MediaType,
    Season,
    SeasonTranslation,
    Title,
    TitleTranslation,
)

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
    # Defaults: cached results from before ratings existed still load
    vote_average: float | None = None
    vote_count: int = 0

    @property
    def key(self) -> str:
        """Unique across movies and shows (they have separate TMDB IDs), e.g. "tv-70523"."""
        return f"{self.media_type}-{self.tmdb_id}"

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
            vote_average=item.get("vote_average"),
            vote_count=item.get("vote_count") or 0,
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
            # /search/multi also finds people; Couch Owl only lists movies and shows
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

    def key(result: SearchResult) -> tuple[int, int]:
        if is_exact_match(result, query):
            return (0, -(result.year or 0))
        return (1, 0)  # sorted() keeps the original order for equal keys

    return sorted(results, key=key)


def is_exact_match(result: SearchResult, query: str) -> bool:
    """Whether the translated or original title equals `query` (see _comparable)."""
    wanted = _comparable(query)
    return wanted in (_comparable(result.title), _comparable(result.original_title))


def _comparable(text: str) -> str:
    """Only letters and digits count, without case and accents:
    'Der Hobbit: Eine Reise' == 'der hobbit - eine reise', 'Spider-Man' == 'Spiderman'.

    Titles made of punctuation only ('?') are compared without case and extra spaces.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    folded = without_accents.casefold()
    return "".join(c for c in folded if c.isalnum()) or " ".join(folded.split())


# --- Titles --------------------------------------------------------------------------------


def get_title(
    media_type: str,
    tmdb_id: int,
    language: str,
    *,
    region: str | None = None,
    force: bool = False,
) -> TitleTranslation:
    """A movie or show in `language`, loaded from TMDB if missing or outdated.

    Data older than TMDB_MAX_AGE is refreshed; `force=True` always refreshes
    ("refresh now" button). Also refreshed if the providers of `region` are missing
    (e.g. after the user changed the region). If TMDB is unreachable, outdated data is
    better than none.
    Raises tmdb.TMDBNotFound if the title does not exist, tmdb.TMDBError if it can't be loaded.
    """
    translation = (
        TitleTranslation.objects.select_related("title")
        .filter(title__media_type=media_type, title__tmdb_id=tmdb_id, language=language)
        .first()
    )
    if (
        translation
        and not force
        and not is_outdated(translation)
        and (region is None or region in translation.title.watch_providers)
    ):
        return translation

    try:
        return fetch_title(media_type, tmdb_id, language)
    except tmdb.TMDBNotFound:
        raise
    except tmdb.TMDBError:
        if translation is None:
            raise
        logger.warning("Showing outdated data for %s %s: TMDB unavailable", media_type, tmdb_id)
        return translation


def fetch_title(media_type: str, tmdb_id: int, language: str) -> TitleTranslation:
    """Load a movie or show from TMDB and store it (shows with seasons and episodes).

    Raises tmdb.TMDBNotFound / tmdb.TMDBError; nothing is changed then.
    """
    data = tmdb.get_client().details(media_type, tmdb_id, language)
    seasons = None
    if media_type == MediaType.TV:
        numbers = [s["season_number"] for s in data.get("seasons") or []]
        seasons = load_seasons(tmdb_id, numbers, language)
    return save_title(media_type, data, language, seasons=seasons)


def best_translations(titles, language: str) -> dict[int, TitleTranslation]:
    """The best stored translation per title (by title id), without asking TMDB.

    Lists show many titles at once; loading each from TMDB would be slow. So lists show
    what is in the database: the user's language if available, otherwise the closest one
    (same fallback order as `localize`, then any). Titles without any translation are
    missing from the result (templates then show the original title).
    """
    return best_texts(TitleTranslation.objects.filter(title__in=titles), language, owner="title_id")


def best_texts(translations, language: str, *, owner: str) -> dict:
    """Pick the best of the stored `translations` per owner (e.g. owner="title_id").

    Same order as `localize`; any other language is better than nothing.
    """
    best: dict[int, tuple[int, object]] = {}
    for translation in translations:
        lang, _sep, country = translation.language.partition("-")
        rank = _language_rank({"iso_639_1": lang, "iso_3166_1": country}, language)
        rank = 5 if rank is None else rank
        key = getattr(translation, owner)
        current = best.get(key)
        if current is None or rank < current[0]:
            best[key] = (rank, translation)
    return {key: translation for key, (_rank, translation) in best.items()}


def is_outdated(translation: TitleTranslation) -> bool:
    return translation.fetched_at < timezone.now() - settings.TMDB_MAX_AGE


@transaction.atomic
def save_title(
    media_type: str, data: dict, language: str, *, seasons: dict[int, dict] | None = None
) -> TitleTranslation:
    """Store a TMDB details response (with translations) for `language`.

    `seasons` (shows only, see load_seasons) replaces the stored seasons and episodes;
    None leaves them as they are.
    """
    is_movie = media_type == MediaType.MOVIE
    original = data.get("original_title" if is_movie else "original_name") or ""
    regions = provider_regions()
    title, _created = Title.objects.update_or_create(
        media_type=media_type,
        tmdb_id=data["id"],
        defaults={
            "original_title": original,
            "original_language": data.get("original_language") or "",
            "release_date": _parse_date(data.get("release_date" if is_movie else "first_air_date")),
            "status": data.get("status") or "",
            "networks": [n["name"] for n in data.get("networks") or [] if n.get("name")],
            "watch_providers": watch_providers(data, regions),
            "release_dates": release_dates(data, regions) if is_movie else {},
            "vote_average": data.get("vote_average"),
            "vote_count": data.get("vote_count") or 0,
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
    if seasons is not None:
        save_seasons(title, seasons, language)
    return translation


# --- Streaming providers ---------------------------------------------------------------------

# TMDB's kinds of offers (JustWatch data)
PROVIDER_KINDS = ("flatrate", "free", "ads", "rent", "buy")


def provider_regions() -> set[str]:
    """Regions whose streaming providers are stored: those of all users, plus the default.

    TMDB sends all ~130 regions at once; storing only these keeps the database small.
    """
    regions = User.objects.exclude(region="").values_list("region", flat=True).distinct()
    return {region.upper() for region in regions} | {default_region()}


# TMDB release types (https://developer.themoviedb.org/reference/movie-release-dates):
# 2 = limited theatrical, 3 = theatrical, 4 = digital. Theatrical prefers the wide release.
RELEASE_TYPES = {"theatrical": (3, 2), "digital": (4,)}


def release_dates(data: dict, regions) -> dict[str, dict]:
    """A movie's theatrical and digital release dates from a TMDB details response
    (`release_dates`) for `regions`: {"DE": {"theatrical": "2027-03-12", "digital": …}}.

    Every wanted region gets an entry, {} if TMDB knows no dates there. Of several dates
    of one type (e.g. festival and wide release) the earliest counts.
    """
    results = (data.get("release_dates") or {}).get("results") or []
    by_region = {entry.get("iso_3166_1"): entry.get("release_dates") or [] for entry in results}
    stored = {}
    for region in sorted(regions):
        entry = {}
        for name, types in RELEASE_TYPES.items():
            for release_type in types:
                days = sorted(
                    day
                    for item in by_region.get(region, [])
                    if item.get("type") == release_type
                    and (day := _parse_date((item.get("release_date") or "")[:10]))
                )
                if days:
                    entry[name] = days[0].isoformat()
                    break
        stored[region] = entry
    return stored


def watch_providers(data: dict, regions) -> dict[str, dict]:
    """The providers from a TMDB details response (`watch/providers`) for `regions`.

    Every wanted region gets an entry, {} if there are no offers there; so a missing
    region means "not loaded yet" (see get_title). Providers are sorted like on JustWatch.
    """
    results = (data.get("watch/providers") or {}).get("results") or {}
    stored = {}
    for region in sorted(regions):
        offers = results.get(region) or {}
        entry = {}
        for kind in PROVIDER_KINDS:
            ranked = sorted(offers.get(kind) or [], key=lambda p: p.get("display_priority", 0))
            providers = [
                {
                    "id": p["provider_id"],
                    "name": p["provider_name"],
                    "logo": p.get("logo_path") or "",
                }
                for p in ranked
                if p.get("provider_id") and p.get("provider_name")
            ]
            if providers:
                entry[kind] = providers
        stored[region] = entry
    return stored


# --- Seasons and episodes ------------------------------------------------------------------


def fallback_languages(language: str) -> list[str]:
    """Languages to ask TMDB for season and episode texts, best first.

    TMDB has no translation list for episodes, and for e.g. "de-AT" it only returns
    placeholders ("Folge 1", no description). Plain "de" returns any German text.
    """
    lang, _sep, country = language.partition("-")
    languages = [language]
    # de-AT: also plain "de"; de-DE and en-US already are the main variant
    if country and country != {"en": "US"}.get(lang, lang.upper()):
        languages.append(lang)
    if lang != "en":
        languages.append("en-US")
    return languages


def load_seasons(tmdb_id: int, numbers: list[int], language: str) -> dict[int, dict]:
    """All seasons of a show with episodes, as {number: TMDB season} with texts in `language`.

    Episodes without a description get name and description from the next language in
    `fallback_languages` (both from the same language, so they match); seasons too.
    The next language is only requested for seasons whose episodes still lack texts
    (season descriptions are often empty everywhere, so they don't trigger a request).
    """
    client = tmdb.get_client()
    seasons: dict[int, dict] = {}
    wanted = list(numbers)
    for lang in fallback_languages(language):
        loaded = {}
        for i in range(0, len(wanted), tmdb.MAX_APPENDED_SEASONS):
            loaded.update(client.seasons(tmdb_id, wanted[i : i + tmdb.MAX_APPENDED_SEASONS], lang))
        if not seasons:
            seasons = loaded
        else:
            _fill_missing_texts(seasons, loaded)
        wanted = [number for number, season in seasons.items() if _lacks_texts(season)]
        if not wanted:
            break
    return seasons


def _lacks_texts(season: dict) -> bool:
    return any(not episode.get("overview") for episode in season.get("episodes") or [])


def _fill_missing_texts(seasons: dict[int, dict], other: dict[int, dict]) -> None:
    for number, season in seasons.items():
        replacement = other.get(number) or {}
        if not season.get("overview") and replacement.get("overview"):
            season["name"] = replacement.get("name") or season.get("name")
            season["overview"] = replacement["overview"]
        replacements = {e.get("episode_number"): e for e in replacement.get("episodes") or []}
        for episode in season.get("episodes") or []:
            found = replacements.get(episode.get("episode_number")) or {}
            if not episode.get("overview") and found.get("overview"):
                episode["name"] = found.get("name") or episode.get("name")
                episode["overview"] = found["overview"]


# TMDB's name for seasons without a name in the requested language, always in English
SEASON_PLACEHOLDER = re.compile(r"Season \d+")


def _season_name(season: dict) -> str:
    """TMDB's season name; its English placeholder ("Season 3") is stored as empty, so
    pages show our translated default name ("Staffel 3") instead."""
    name = season.get("name") or ""
    return "" if SEASON_PLACEHOLDER.fullmatch(name) else name


def save_seasons(show: Title, seasons: dict[int, dict], language: str) -> None:
    """Replace the stored seasons and episodes of `show` with `seasons` (see load_seasons).

    Bulk "upserts" (insert or update in one statement): long-running shows have hundreds
    of episodes, and one query per episode would be slow. Seasons and episodes that TMDB
    no longer lists are deleted, together with their watched marks.
    """
    Season.objects.bulk_create(
        [
            Season(show=show, number=number, air_date=_parse_date(data.get("air_date")))
            for number, data in seasons.items()
        ],
        update_conflicts=True,
        unique_fields=["show", "number"],
        update_fields=["air_date"],
    )
    show.seasons.exclude(number__in=list(seasons)).delete()
    season_ids = dict(show.seasons.values_list("number", "pk"))
    SeasonTranslation.objects.bulk_create(
        [
            SeasonTranslation(
                season_id=season_ids[number],
                language=language,
                name=_season_name(data),
                overview=data.get("overview") or "",
            )
            for number, data in seasons.items()
        ],
        update_conflicts=True,
        unique_fields=["season", "language"],
        update_fields=["name", "overview"],
    )

    episodes = {
        (number, e["episode_number"]): e
        for number, data in seasons.items()
        for e in data.get("episodes") or []
        if e.get("episode_number") is not None
    }
    Episode.objects.bulk_create(
        [
            Episode(
                season_id=season_ids[season_number],
                number=episode_number,
                tmdb_id=data.get("id"),
                air_date=_parse_date(data.get("air_date")),
                runtime=data.get("runtime"),
            )
            for (season_number, episode_number), data in episodes.items()
        ],
        update_conflicts=True,
        unique_fields=["season", "number"],
        update_fields=["tmdb_id", "air_date", "runtime"],
    )
    stored = Episode.objects.filter(season__show=show).values_list("season__number", "number", "pk")
    episode_ids = {}
    gone = []
    for season_number, episode_number, pk in stored:
        if (season_number, episode_number) in episodes:
            episode_ids[season_number, episode_number] = pk
        else:
            gone.append(pk)
    Episode.objects.filter(pk__in=gone).delete()
    EpisodeTranslation.objects.bulk_create(
        [
            EpisodeTranslation(
                episode_id=episode_ids[key],
                language=language,
                name=data.get("name") or "",
                overview=data.get("overview") or "",
            )
            for key, data in episodes.items()
        ],
        update_conflicts=True,
        unique_fields=["episode", "language"],
        update_fields=["name", "overview"],
    )


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
