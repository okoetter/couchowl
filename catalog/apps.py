from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CatalogConfig(AppConfig):
    """Movies and shows from TMDB: API client, search, poster proxy."""

    name = "catalog"
    verbose_name = _("Movies and shows")
