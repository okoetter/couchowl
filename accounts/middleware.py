from django.utils import translation

from .regions import default_region, region_from_accept_language


class UserLanguageMiddleware:
    """Apply the logged-in user's region and interface language.

    Django's LocaleMiddleware picks the language from the browser
    (Accept-Language header) for visitors who are not logged in.
    For logged-in users, their profile wins: an explicitly chosen language,
    otherwise the main language of their region (see accounts/regions.py).
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
            translation.activate(user.effective_ui_language)
            request.LANGUAGE_CODE = translation.get_language()
        return self.get_response(request)
