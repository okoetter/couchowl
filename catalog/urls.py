from django.urls import path, register_converter

from . import views


class MediaTypeConverter:
    """URL part "movie" or "tv" (TMDB's names), e.g. /movie/155/ or /tv/70523/."""

    regex = "movie|tv"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(MediaTypeConverter, "media")

app_name = "catalog"

urlpatterns = [
    path("search/", views.search, name="search"),
    path("posters/<str:size>/<str:filename>", views.poster, name="poster"),
    # Lists
    path("lists/", views.lists, name="lists"),
    path("lists/<int:pk>/", views.list_detail, name="list_detail"),
    path("lists/<int:pk>/rename/", views.list_rename, name="list_rename"),
    path("lists/<int:pk>/delete/", views.list_delete, name="list_delete"),
    path("lists/<int:pk>/layout/", views.list_layout, name="list_layout"),
    path(
        "lists/<int:pk>/items/<int:item_pk>/remove/",
        views.list_item_remove,
        name="list_item_remove",
    ),
    path(
        "lists/<int:pk>/items/<int:item_pk>/watched/",
        views.list_item_watched,
        name="list_item_watched",
    ),
    # Movies and shows
    path("<media:media_type>/<int:tmdb_id>/", views.title_detail, name="title_detail"),
    path("<media:media_type>/<int:tmdb_id>/lists/", views.title_lists, name="title_lists"),
    path(
        "<media:media_type>/<int:tmdb_id>/lists/new/",
        views.title_list_create,
        name="title_list_create",
    ),
    path(
        "<media:media_type>/<int:tmdb_id>/lists/<int:list_pk>/",
        views.title_list_membership,
        name="title_list_membership",
    ),
    path("movie/<int:tmdb_id>/watched/", views.movie_watched, name="movie_watched"),
]
