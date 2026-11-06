from django.utils import translation


class UserLanguageMiddleware:
    """Activate the interface language from the logged-in user's profile.

    Django's LocaleMiddleware picks the language from the browser
    (Accept-Language header). For logged-in users, their profile setting wins.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.ui_language:
            translation.activate(user.ui_language)
            request.LANGUAGE_CODE = translation.get_language()
        return self.get_response(request)
