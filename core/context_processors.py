from django.conf import settings


def watchit(request):
    """Values available in every template."""
    user = getattr(request, "user", None)
    theme = user.theme if user is not None and user.is_authenticated else "auto"
    return {
        "WATCHIT_VERSION": settings.VERSION,
        "theme": theme,
        "email_enabled": settings.EMAIL_ENABLED,
    }
