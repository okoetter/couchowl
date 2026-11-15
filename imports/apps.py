from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ImportsConfig(AppConfig):
    """Batch import: paste a list of titles, check the matches, import them."""

    name = "imports"
    verbose_name = _("Batch import")
