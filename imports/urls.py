from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("import/", views.page, name="page"),
    path("import/step/", views.step, name="step"),
    path("import/start/", views.start, name="start"),
    path("import/discard/", views.discard, name="discard"),
    path("import/lines/<int:pk>/", views.line, name="line"),
]
