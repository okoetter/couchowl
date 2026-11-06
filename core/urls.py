from django.urls import path
from django.utils.translation import gettext_lazy as _

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # Placeholders until the real pages exist (milestones 2-6)
    path("lists/", views.placeholder, {"title": _("Lists")}, name="lists"),
    path("upcoming/", views.placeholder, {"title": _("Upcoming")}, name="upcoming"),
    path("search/", views.placeholder, {"title": _("Search")}, name="search"),
    path("healthz/", views.health, name="health"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
]
