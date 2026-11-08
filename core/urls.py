from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("watching/<int:tmdb_id>/next/", views.watch_next, name="watch_next"),
    path("upcoming/", views.upcoming, name="upcoming"),
    path("upcoming/refresh/", views.upcoming_refresh, name="upcoming_refresh"),
    path("healthz/", views.health, name="health"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
]
