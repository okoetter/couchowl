from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET


def dashboard(request):
    return render(request, "core/dashboard.html")


def placeholder(request, title):
    """Temporary page for navigation targets that are built in later milestones."""
    return render(request, "core/placeholder.html", {"page_title": title})


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
