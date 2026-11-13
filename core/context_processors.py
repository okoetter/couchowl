from django.conf import settings


def app(request):
    """Values available in every template."""
    user = getattr(request, "user", None)
    theme = user.theme if user is not None and user.is_authenticated else "auto"
    return {
        "APP_NAME": settings.APP_NAME,
        "APP_VERSION": settings.VERSION,
        "theme": theme,
        "email_enabled": settings.EMAIL_ENABLED,
    }
