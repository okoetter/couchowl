import time

from django.utils import translation

from .regions import default_region, language_with_region, region_from_accept_language


class UserLanguageMiddleware:
    """Apply the logged-in user's region and interface language.

    Django's LocaleMiddleware picks the language from the browser
    (Accept-Language header) for visitors who are not logged in.
    For logged-in users, their profile wins: an explicitly chosen language,
    otherwise the main language of their region (see accounts/regions.py).
    The active language also carries the region (e.g. "en-gb"): texts come from the
    "en" translation, date formats from the country (01/12/2017 instead of 12/01/2017).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            if not user.region:
                # First request of a new user: detect the country from the browser once
                header = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
                user.region = region_from_accept_language(header) or default_region()
                user.save(update_fields=["region"])
            translation.activate(
                language_with_region(user.effective_ui_language, user.effective_region)
            )
            request.LANGUAGE_CODE = translation.get_language()
        return self.get_response(request)


class SessionRenewalMiddleware:
    """Keep users logged in while they use Couch Owl: SESSION_DAYS counts from the last visit.

    Django only moves a session's expiry when the session data changes, so without this a
    login would end SESSION_DAYS after logging in, however often someone visits.
    Saving the session on every request (SESSION_SAVE_EVERY_REQUEST) would do the same with
    a database write per request; this changes the session at most once a day instead.
    Saving a changed session sets a new expiry in the database and a new cookie.
    """

    KEY = "renewed_at"
    INTERVAL = 24 * 3600  # seconds

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = int(time.time())
            if now - request.session.get(self.KEY, 0) >= self.INTERVAL:
                request.session[self.KEY] = now
        return self.get_response(request)
