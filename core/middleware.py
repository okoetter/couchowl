import time

from django.conf import settings

# Methods that only read; every other request may change data
SAFE_METHODS = ("GET", "HEAD", "OPTIONS", "TRACE")


class DataVersionMiddleware:
    """Let pages restored by the back button notice that data changed since they were made.

    Browsers show the previous page from their caches (bfcache or HTTP cache) without asking
    the server, so after following a show and going back, the list would still show the old
    state. Every successful change (POST) stores a new version in a cookie. Pages carry the
    version they were rendered with (`<main data-version>`, see base.html); couchowl.js
    compares both when a page comes back and reloads the page content if they differ.
    """

    COOKIE = "couchowl_version"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        changes = request.method not in SAFE_METHODS
        # A page rendered by the changing request itself already shows the new state
        request.data_version = (
            str(time.time_ns()) if changes else request.COOKIES.get(self.COOKIE, "")
        )
        response = self.get_response(request)
        if changes and response.status_code < 400:
            # Not HttpOnly: couchowl.js reads it. Ends with the browser session.
            response.set_cookie(
                self.COOKIE,
                request.data_version,
                secure=settings.SESSION_COOKIE_SECURE,
                httponly=False,
                samesite="Lax",
            )
        return response
