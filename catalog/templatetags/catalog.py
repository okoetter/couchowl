"""Template helpers for movies and shows. Usage: {% load catalog %}"""

from django import template
from django.utils.formats import number_format
from django.utils.html import format_html
from django.utils.translation import get_language, gettext, ngettext

from accounts.regions import country_name
from catalog.posters import poster_url

register = template.Library()


@register.simple_tag
def poster(poster_path, size="w185"):
    """URL of a poster via our proxy, e.g. {% poster result.poster_path "w92" %}."""
    return poster_url(poster_path or "", size)


# Overviews (search, lists) hide ratings with fewer votes: "10.0 from 2 votes" says little
MIN_VOTES = 10


@register.simple_tag
def rating(item, votes=False):
    """TMDB rating like "★ 8.4" for a Title or SearchResult, formatted for the user's
    region (8,4 in Germany). Overviews: {% rating item %}, nothing below MIN_VOTES.
    Detail page: {% rating title votes=True %} adds the number of votes, from 1 vote.
    """
    count = item.vote_count or 0
    if item.vote_average is None or count < (1 if votes else MIN_VOTES):
        return ""
    average = number_format(item.vote_average, decimal_pos=1)
    count_text = number_format(count, force_grouping=True)
    label = ngettext(
        "TMDB rating: %(average)s of 10 (%(count)s vote)",
        "TMDB rating: %(average)s of 10 (%(count)s votes)",
        count,
    ) % {"average": average, "count": count_text}
    # "★ 8.4" and "(1,234 votes)" never break apart, but may go to separate lines
    # (narrow phones, wide fonts)
    text = format_html('<span class="nowrap">★ {}</span>', average)
    if votes:
        votes_text = ngettext("(%(count)s vote)", "(%(count)s votes)", count) % {
            "count": count_text
        }
        text = format_html('{} <span class="nowrap">{}</span>', text, votes_text)
    # Screen readers get the long label instead of "star 8.4"
    return format_html(
        '<span class="rating" title="{}"><span aria-hidden="true">{}</span>'
        '<span class="visually-hidden">{}</span></span>',
        label,
        text,
        label,
    )


# How age ratings of a region are labeled; elsewhere TMDB's value as is ("PG-13", "TV-MA").
# TMDB sends German ratings as plain ages ("16"), but everyone knows them as "FSK 16".
CERTIFICATION_LABELS = {"DE": "FSK {}"}


@register.simple_tag
def certification(title, region):
    """Age rating of a Title in `region` as a small framed label, e.g. "FSK 16" or
    "PG-13", with the country as tooltip. Empty if TMDB knows none for the region.
    Usage: {% certification title region as rating %}{% if rating %} · {{ rating }}{% endif %}
    """
    value = (title.certifications or {}).get(region)
    if not value:
        return ""
    text = CERTIFICATION_LABELS.get(region, "{}").format(value)
    label = gettext("Age rating (%(country)s)") % {"country": country_name(region, get_language())}
    # Screen readers get "Age rating (Germany): FSK 16"; the tooltip alone is not read
    return format_html(
        '<span class="certification" title="{}"><span aria-hidden="true">{}</span>'
        '<span class="visually-hidden">{}: {}</span></span>',
        label,
        text,
        label,
        text,
    )
