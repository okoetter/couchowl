from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("search/", views.search, name="search"),
    path("posters/<str:size>/<str:filename>", views.poster, name="poster"),
]
