"""Streaming providers for display. Stored per region in Title.watch_providers (see
catalog.services.watch_providers); the data comes from JustWatch via TMDB, so pages that
show it must name JustWatch as the source.
"""

from dataclasses import dataclass

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


def link(title: Title, region: str) -> str:
    """TMDB's page with all offers in `region` ('' if unknown)."""
    return (title.watch_providers.get(region) or {}).get("link", "")


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
