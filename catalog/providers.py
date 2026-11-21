"""Streaming providers for display. Stored per region in Title.watch_providers (see
catalog.services.watch_providers); the data comes from JustWatch via TMDB, so pages that
show it must name JustWatch as the source.
"""

from dataclasses import dataclass
from datetime import date

from django.utils.translation import gettext_lazy as _

from .models import Title

# Groups on the detail page, in this order: (label, TMDB kinds)
GROUPS = (
    (_("Subscription"), ("flatrate",)),
    (_("Free"), ("free", "ads")),
    (_("Rent"), ("rent",)),
    (_("Buy"), ("buy",)),
)
# Kinds that count as "where it airs" next to the networks (announcements, upcoming)
STREAMING_KINDS = ("flatrate", "free", "ads")


@dataclass
class ProviderGroup:
    label: str
    providers: list[dict]  # {"id", "name", "logo"}


def offers(title: Title, region: str) -> list[ProviderGroup]:
    """Non-empty provider groups of `title` in `region`; a provider appears once per group."""
    stored = title.watch_providers.get(region) or {}
    groups = []
    for label, kinds in GROUPS:
        seen = set()
        providers = []
        for kind in kinds:
            for provider in stored.get(kind) or []:
                if provider["id"] not in seen:
                    seen.add(provider["id"])
                    providers.append(provider)
        if providers:
            groups.append(ProviderGroup(label=label, providers=providers))
    return groups


def sources(title: Title, region: str) -> list[str]:
    """Where a show airs, for one-line display: its networks, then streaming providers.

    Variants of a name already listed are left out ("Netflix Standard with Ads" after
    "Netflix", "Amazon Prime Video with Ads" after "Amazon Prime Video"), so the line
    stays short. Rent and buy offers are not included.
    """
    names = list(title.networks)
    stored = title.watch_providers.get(region) or {}
    for kind in STREAMING_KINDS:
        for provider in stored.get(kind) or []:
            name = provider["name"]
            if not any(_is_variant(name, known) for known in names):
                names.append(name)
    return names


def _is_variant(name: str, known: str) -> bool:
    """'Netflix' and 'Netflix Standard with Ads' are variants of 'Netflix'; 'ZDFneo' of
    'ZDF' is not (whole words only, case-insensitive)."""
    name, known = name.casefold(), known.casefold()
    return name == known or name.startswith(known + " ")


# TMDB statuses of titles that are out (a missing date doesn't mean "not out yet" then)
RELEASED_STATUSES = {"Released", "Returning Series", "Ended", "Canceled"}


@dataclass
class Availability:
    """What the detail page says instead of offers when JustWatch knows none in a region.

    JustWatch usually lists a title only once it can be watched, so before the start the
    page names the start date and, for shows, the networks (the original broadcaster,
    worldwide: an HBO show may run elsewhere in the region, so this is not an offer).
    """

    state: str  # one of the constants below
    starts: date | None = None  # shows: first episode; movies: TMDB's own release date
    theatrical: date | None = None  # movies: theatrical release in the region
    digital: date | None = None  # movies: digital release in the region
    networks: str = ""  # shows: "HBO" or "HBO, Max"

    SHOW_STARTS = "show_starts"  # show starts on `starts`
    SHOW_NO_DATE = "show_no_date"  # show not started, no date yet
    CINEMA = "cinema"  # movie comes to cinemas in the region (and digital later)
    DIGITAL = "digital"  # movie comes out digitally in the region
    RELEASE = "release"  # movie comes out, but no date for the region yet
    NO_DATE = "no_date"  # movie not out, no date yet
    NONE = "none"  # out, but no offers known in the region


def availability(title: Title, region: str, today: date) -> Availability:
    """What to say about `title` in `region` when there are no streaming offers there."""
    if not title.is_movie:
        networks = ", ".join(title.networks)
        if title.release_date and title.release_date > today:
            return Availability(
                Availability.SHOW_STARTS, starts=title.release_date, networks=networks
            )
        if not title.release_date and title.status not in RELEASED_STATUSES:
            return Availability(Availability.SHOW_NO_DATE, networks=networks)
        return Availability(Availability.NONE, networks=networks)

    dates = title.release_dates.get(region) or {}
    theatrical = _date(dates.get("theatrical"))
    digital = _date(dates.get("digital"))
    if digital and digital <= today:
        digital = None  # already out digitally: not worth mentioning
    if theatrical and theatrical > today:
        return Availability(Availability.CINEMA, theatrical=theatrical, digital=digital)
    if digital:
        return Availability(Availability.DIGITAL, digital=digital)
    if not theatrical and title.release_date and title.release_date > today:
        return Availability(Availability.RELEASE, starts=title.release_date)
    if not theatrical and not title.release_date and title.status not in RELEASED_STATUSES:
        return Availability(Availability.NO_DATE)
    return Availability(Availability.NONE)


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None
