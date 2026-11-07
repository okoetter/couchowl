"""
Django settings for watchit.

All configuration comes from environment variables (see .env.example).
Without a .env file, safe-ish development defaults are used.
"""

from datetime import timedelta
from pathlib import Path

import environ

from config.mail import mailer_from_url
from config.version import get_version

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
# Read .env if present (local development). In Docker, variables come from compose.
environ.Env.read_env(BASE_DIR / ".env")

VERSION = get_version()

# --- Core ---------------------------------------------------------------------

DEBUG = env.bool("DEBUG", default=False)
SECRET_KEY = env("SECRET_KEY", default="django-insecure-dev-only-change-me" if DEBUG else None)
# localhost is always allowed so the container healthcheck works with any configuration
ALLOWED_HOSTS = [*env.list("ALLOWED_HOSTS", default=[]), "localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Directory for all runtime data: database, poster cache, backups.
# In Docker this is a volume mounted at /data.
DATA_DIR = Path(env("DATA_DIR", default=str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "axes",
    "core",
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Every page requires login unless the view is marked with @login_not_required
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    # Must come after AuthenticationMiddleware: applies the user's profile language
    "accounts.middleware.UserLanguageMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Should be last: turns axes lockouts into a proper "locked out" response
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.watchit",
            ],
        },
    },
]

# Form fields in Pico's order: label, input, errors, help text (core/templates/forms/)
FORM_RENDERER = "core.forms.FormRenderer"

# --- Database -----------------------------------------------------------------
# SQLite by default; PostgreSQL via e.g. DATABASE_URL=postgres://user:pass@db:5432/watchit

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{DATA_DIR / 'db.sqlite3'}"),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth ---------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTHENTICATION_BACKENDS = [
    # Must be first: rejects logins while a username/IP combination is locked out
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# How long an invitation link stays valid
INVITATION_EXPIRY_DAYS = env.int("INVITATION_EXPIRY_DAYS", default=7)
# How long a password reset link stays valid (Django setting, in seconds)
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT_HOURS", default=24) * 3600
# Max. "forgot password" requests per IP address and hour
PASSWORD_RESET_RATE_LIMIT = 5

# --- Brute-force protection (django-axes) ---------------------------------------
# After AXES_FAILURE_LIMIT failed logins, the combination of username and IP address
# is locked for AXES_COOLOFF_TIME. Admins can unlock early: manage.py axes_reset
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = timedelta(minutes=env.int("AXES_COOLOFF_MINUTES", default=60))
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "accounts/locked_out.html"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalization -----------------------------------------------------
# UI texts live in locale/<lang>/LC_MESSAGES/django.po. Source strings are English.

# Language names in their own language, so everyone finds theirs
LANGUAGES = [
    ("en", "English"),
    ("de", "Deutsch"),
]
# Fallback interface language: for visitors whose browser language has no translation,
# and for users whose region's main language has none
LANGUAGE_CODE = env("DEFAULT_LANGUAGE", default="en")
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True

TIME_ZONE = env("TIME_ZONE", default="Europe/Berlin")
USE_TZ = True

# Region for new users whose browser doesn't reveal a country (empty: US).
# Languages for movie/show texts are derived from the region (accounts/regions.py).
DEFAULT_REGION = env("DEFAULT_REGION", default="")

# --- Cache ----------------------------------------------------------------------
# File-based, so all gunicorn worker processes share it (used for rate limits).

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": DATA_DIR / "cache",
    }
}

# --- Static files -------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- E-mail -------------------------------------------------------------------
# Optional. Without EMAIL_URL, features that need e-mail are hidden.
# Development: EMAIL_URL=consolemail://  (mails are printed to the terminal)

EMAIL_ENABLED = "EMAIL_URL" in env
MAILERS = {"default": mailer_from_url(env("EMAIL_URL"))} if EMAIL_ENABLED else {}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="watchit <watchit@localhost>")

# --- Logging ------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
