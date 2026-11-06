"""Settings for the test suite: independent of any local .env file."""

import os
import tempfile

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="watchit-test-"))

from config.settings import *  # noqa: E402, F403

# Tests should not depend on a prior `collectstatic` run
STATIC_ROOT = DATA_DIR / "staticfiles"  # noqa: F405
STATIC_ROOT.mkdir(exist_ok=True)
EMAIL_ENABLED = True
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
LANGUAGE_CODE = "de"
DEFAULT_TMDB_LANGUAGE = "de-DE"
DEFAULT_REGION = ""
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only
