import logging

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.utils.cache import patch_cache_control, patch_vary_headers
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET

from accounts.throttle import hit

from . import posters, services, tmdb

logger = logging.getLogger(__name__)


def _is_htmx_fragment_request(request) -> bool:
    """htmx asks for a page fragment; a history restore (back button) needs the full page."""
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


@require_GET
def search(request):
    """Search page. Live search (htmx) only gets the results fragment.

    Also works without JavaScript: the form submits ?q=… and gets the full page.
    """
    query = services.normalize_query(request.GET.get("q", ""))
    results, error = [], None
    if len(query) >= services.MIN_QUERY_LENGTH:
        if not hit(f"search:{request.user.pk}", settings.SEARCH_RATE_LIMIT, 60):
            error = _("Too many searches in a short time. Please wait a moment.")
        else:
            try:
                results = services.search(query, request.user.effective_tmdb_language)
            except tmdb.TMDBNotConfigured:
                error = _("Search is not available: the administrator has not set up TMDB yet.")
            except tmdb.TMDBError:
                logger.exception("TMDB search failed")
                error = _("TMDB can't be reached right now. Please try again later.")

    context = {
        "query": query,
        "results": results,
        "error": error,
        "min_query_length": services.MIN_QUERY_LENGTH,
    }
    template = "catalog/search.html"
    if _is_htmx_fragment_request(request):
        template += "#results"
    response = render(request, template, context)
    # Browsers must not mix up cached fragment and full page (e.g. on "back")
    patch_vary_headers(response, ["HX-Request"])
    return response


@require_GET
def poster(request, size, filename):
    """Serve a TMDB poster from the local cache (downloaded on first request)."""
    if not posters.is_valid(size, filename):
        raise Http404
    try:
        path = posters.cached_poster(size, filename)
    except tmdb.TMDBNotFound:
        raise Http404 from None
    except tmdb.TMDBError:
        logger.warning("Could not load poster %s/%s from TMDB", size, filename, exc_info=True)
        return HttpResponse(status=502)

    response = FileResponse(path.open("rb"), content_type=posters.content_type(filename))
    # The file behind a TMDB path never changes. "private": only for logged-in users.
    patch_cache_control(response, private=True, max_age=365 * 24 * 3600, immutable=True)
    return response
