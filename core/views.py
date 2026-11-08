from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET, require_POST

from catalog import dashboard as dashboard_rules
from catalog import shows
from catalog.models import Episode, MediaType, Title


def _is_htmx_fragment_request(request) -> bool:
    """htmx asks for a page fragment; a history restore (back button) needs the full page."""
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


def _dashboard_context(request) -> dict:
    language = request.user.effective_tmdb_language
    return {
        "watching": dashboard_rules.continue_watching(request.user, language),
        "announcements": dashboard_rules.announcements(request.user, language),
        "announcement_months": settings.ANNOUNCEMENT_MONTHS,
        "follows_shows": shows.followed_shows(request.user).exists(),
    }


@require_GET
def dashboard(request):
    """Start page: shows to continue watching and announced seasons (database only)."""
    return render(request, "core/dashboard.html", _dashboard_context(request))


@require_POST
def watch_next(request, tmdb_id):
    """Check button on the dashboard: mark the show's next episode as watched (today).

    `undo=<episode id>` takes it back. htmx gets as little as possible (posters must not
    flicker): only the entry's text and button, or the entry disappears when the show is
    caught up; plus the message "S2 E5 watched · Undo".
    """
    show = get_object_or_404(Title, media_type=MediaType.TV, tmdb_id=tmdb_id)
    if undo := request.POST.get("undo"):
        episode = get_object_or_404(Episode, pk=undo, season__show=show)
        shows.unmark_episodes(request.user, [episode])
        if not _is_htmx_fragment_request(request):
            return redirect("core:dashboard")
        # The whole section ("morph" keeps the posters): the entry may have disappeared
        response = render(request, "core/dashboard.html#watching", _dashboard_context(request))
        response.content += _toast(request, show, None).encode()
        return response

    episode = shows.watch_next(request.user, show)
    if not _is_htmx_fragment_request(request):
        if episode is not None:
            messages.success(request, _("%(episode)s watched.") % {"episode": episode.code})
        return redirect("core:dashboard")

    context = _dashboard_context(request)
    entry = next((e for e in context["watching"] if e.show.pk == show.pk), None)
    if not context["watching"]:
        response = render(request, "core/dashboard.html#watching", context)
        response["HX-Retarget"] = "#watching"
        response["HX-Reswap"] = "innerHTML"
    elif entry is None:
        response = HttpResponse("")
        response["HX-Retarget"] = "closest li"
        response["HX-Reswap"] = "outerHTML"
    else:
        response = render(request, "core/dashboard.html#watching-entry", {"entry": entry})
    if episode is not None:
        response.content += _toast(request, show, episode).encode()
    patch_vary_headers(response, ["HX-Request"])
    return response


def _toast(request, show: Title, episode: Episode | None) -> str:
    """The "S2 E5 watched · Undo" message (htmx puts it in place by its id)."""
    context = {
        "episode": episode,
        "undo_url": reverse("core:watch_next", args=[show.tmdb_id]),
        "undo_target": "#watching",
    }
    return render_to_string("catalog/_toast.html", context, request=request)


def placeholder(request, title):
    """Temporary page for navigation targets that are built in later milestones."""
    return render(request, "core/placeholder.html", {"page_title": title})


@login_not_required
@require_GET
def health(request):
    """Used by the Docker healthcheck. Verifies the database is reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse(
        {"status": "ok" if db_ok else "error", "version": settings.VERSION},
        status=200 if db_ok else 503,
    )


@login_not_required
@require_GET
@cache_control(max_age=86400)
def manifest(request):
    """PWA web app manifest. Served by Django so name and start URL are translatable."""
    data = {
        "name": "watchit",
        "short_name": "watchit",
        "description": _("Your watchlist for movies and TV shows"),
        "lang": request.LANGUAGE_CODE,
        "start_url": reverse("core:dashboard"),
        "scope": "/",
        "display": "standalone",
        "background_color": "#1a2b4a",
        "theme_color": "#1a2b4a",
        "icons": [
            {"src": static("core/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("core/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {
                "src": static("core/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
            {"src": static("core/icon.svg"), "sizes": "any", "type": "image/svg+xml"},
        ],
    }
    return JsonResponse(data, content_type="application/manifest+json")
