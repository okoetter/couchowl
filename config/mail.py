"""Translate a single EMAIL_URL into Django's MAILERS configuration (Django >= 6.1)."""

import environ

# django-environ key -> SMTP backend OPTIONS key
_SMTP_OPTIONS = {
    "EMAIL_HOST": "host",
    "EMAIL_PORT": "port",
    "EMAIL_HOST_USER": "username",
    "EMAIL_HOST_PASSWORD": "password",
    "EMAIL_USE_TLS": "use_tls",
    "EMAIL_USE_SSL": "use_ssl",
}


def mailer_from_url(url: str) -> dict:
    """'smtp+tls://user:pw@host:587' -> {"BACKEND": ..., "OPTIONS": {...}}.

    Other schemes (consolemail://, filemail://, memorymail://, dummymail://)
    map to the matching Django backends without options.
    """
    config = environ.Env.email_url_config(url)
    backend = config["EMAIL_BACKEND"]
    mailer = {"BACKEND": backend}
    if backend.endswith("smtp.EmailBackend"):
        mailer["OPTIONS"] = {
            option: config[key]
            for key, option in _SMTP_OPTIONS.items()
            if config.get(key) not in (None, "")
        }
    return mailer
