from django.urls import path
from django.utils.translation import gettext_lazy as _

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("watching/<int:tmdb_id>/next/", views.watch_next, name="watch_next"),
    # Placeholder until the real page exists (milestone 6)
    path("upcoming/", views.placeholder, {"title": _("Upcoming")}, name="upcoming"),
    path("healthz/", views.health, name="health"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
]
