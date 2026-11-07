"""Template helpers for movies and shows. Usage: {% load catalog %}"""

from django import template

from catalog.posters import poster_url

register = template.Library()


@register.simple_tag
def poster(poster_path, size="w185"):
    """URL of a poster via our proxy, e.g. {% poster result.poster_path "w92" %}."""
    return poster_url(poster_path or "", size)
