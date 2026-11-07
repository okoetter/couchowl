"""Region (country) is the main setting; languages are derived from it.

Country data (names, official languages) comes from Babel (Unicode CLDR).
"""

import unicodedata
from functools import cache

from babel import Locale, UnknownLocaleError
from babel.core import get_global
from babel.languages import get_official_languages
from django.conf import settings
from django.utils.translation.trans_real import parse_accept_lang_header

from .countries import COUNTRY_CODES

FALLBACK_REGION = "US"


def primary_language(region: str) -> str | None:
    """Most widely spoken official language of a country: 'AT' -> 'de', 'BE' -> 'nl'."""
    languages = get_official_languages(region.upper(), de_facto=True)
    return languages[0] if languages else None


def ui_language_for_region(region: str) -> str:
    """Interface language for a country, if watchit has a translation, else the default."""
    language = primary_language(region)
    if language in dict(settings.LANGUAGES):
        return language
    return settings.LANGUAGE_CODE


def tmdb_language_for_region(region: str) -> str:
    """TMDB language code for a country: 'AT' -> 'de-AT', 'IN' -> 'hi-IN'."""
    region = region.upper()
    return f"{primary_language(region) or 'en'}-{region}"


def region_from_accept_language(header: str) -> str | None:
    """Guess the country from the browser's Accept-Language header.

    Uses the preferred language: 'de-AT,de;q=0.9' -> 'AT'. Without a country part,
    the language's most likely country is used: 'de' -> 'DE', 'en' -> 'US'.
    """
    for language, _quality in parse_accept_lang_header(header or ""):
        if language == "*":
            continue
        parts = language.replace("_", "-").split("-")
        country = next((p.upper() for p in parts[1:] if len(p) == 2), None)
        if country is None:
            likely = get_global("likely_subtags").get(parts[0].lower(), "")
            country = likely.split("_")[-1] if likely else None
        if country in COUNTRY_CODES:
            return country
        return None  # only the most preferred language counts
    return None


def default_region() -> str:
    """Server default region (DEFAULT_REGION), or US."""
    region = settings.DEFAULT_REGION.upper()
    return region if region in COUNTRY_CODES else FALLBACK_REGION


@cache
def language_with_region(language: str, region: str) -> str:
    """Language code plus country, e.g. ("en", "GB") -> "en-gb".

    Django takes texts from the "en" translation and date formats from the country's
    format module where it has one (en_GB: 01/12/2017); otherwise the language's.
    """
    if "-" in language or not region:
        return language
    return f"{language}-{region.lower()}"


def country_choices(language: str) -> list[tuple[str, str]]:
    """All countries as (code, name) with names in the given language, sorted by name."""
    # Only the language: Babel doesn't know every combination (e.g. "de-us")
    language = language.split("-")[0]
    try:
        names = Locale.parse(language).territories
    except UnknownLocaleError, ValueError:
        names = Locale("en").territories
    choices = [(code, names.get(code, code)) for code in COUNTRY_CODES]
    return sorted(choices, key=lambda choice: _sort_key(choice[1]))


def _sort_key(name: str) -> str:
    # 'Österreich' sorts with 'O', not after 'Z'
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
