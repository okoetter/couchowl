"""Page /import/: paste → preview → import → result, all on one page (see rules.py)."""

import logging

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from catalog import tmdb

from . import rules
from .forms import ImportForm
from .models import Import, ImportLine

logger = logging.getLogger(__name__)


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _back_to_page(request, anchor=""):
    """To the import page: htmx loads it as a whole page ("HX-Redirect"), else redirect."""
    url = reverse("imports:page") + anchor
    if _is_htmx(request):
        response = HttpResponse()
        response["HX-Redirect"] = url
        return response
    return redirect(url)


def _tmdb_error(error: tmdb.TMDBError) -> str:
    if isinstance(error, tmdb.TMDBNotConfigured):
        return _("The administrator has not set up TMDB yet.")
    return _("TMDB can't be reached right now. Please try again later.")


def page(request):
    """The paste form, or the current import in whatever state it is."""
    batch = Import.objects.filter(user=request.user).first()
    if batch is None:
        return _paste(request)
    if request.method == "POST":  # e.g. the paste form sent from a second tab
        return redirect("imports:page")
    context = {"batch": batch}
    if batch.state == Import.State.PREVIEW:
        lines, summary = rules.preview(request.user, batch)
        context.update(lines=lines, summary=summary)
    elif batch.state == Import.State.DONE:
        context.update(result=rules.result(batch), target=_target(request, batch))
    else:
        context["progress"] = rules.progress(batch)
    return render(request, "imports/import.html", context)


def _target(request, batch: Import):
    if not batch.list_name:
        return None
    return request.user.lists.filter(name__iexact=batch.list_name).first()


def _paste(request):
    if request.method == "POST":
        form = ImportForm(request.POST, user=request.user)
        if form.is_valid():
            rules.create_import(
                request.user,
                form.cleaned_data["lines"],
                list_name=form.list_name,
                watched=form.cleaned_data["watched"],
                follow=form.cleaned_data["follow"],
            )
            return redirect("imports:page")
    else:
        # Opened from a list: that list is preselected
        form = ImportForm(user=request.user, initial={"target": request.GET.get("list", "")})
    return render(request, "imports/import.html", {"form": form})


@require_POST
def step(request):
    """Search or import the next chunk of lines (htmx calls this again and again).

    Returns the progress bar, which asks for the next chunk as soon as it is shown; after
    the last chunk the whole page is reloaded. Without JavaScript: back to the page.
    """
    batch = Import.objects.filter(user=request.user).first()
    if batch is None or batch.state not in (Import.State.ANALYZING, Import.State.IMPORTING):
        return _back_to_page(request)
    error = ""
    try:
        current = rules.step(request.user, batch)
    except tmdb.TMDBError as e:
        if not isinstance(e, tmdb.TMDBNotConfigured):
            logger.exception("Batch import: TMDB request failed")
        error = _tmdb_error(e)
        current = rules.progress(batch)
    if batch.state not in (Import.State.ANALYZING, Import.State.IMPORTING):
        return _back_to_page(request)
    if not _is_htmx(request):
        if error:
            messages.error(request, error)
        return redirect("imports:page")
    context = {"batch": batch, "progress": current, "error": error}
    response = render(request, "imports/import.html#progress", context)
    patch_vary_headers(response, ["HX-Request"])
    return response


@require_POST
def line(request, pk):
    """Preview: change one line (`choice`, `watched`, `follow` or `query` = search again).

    htmx gets the line and the counts; without JavaScript the page is reloaded.
    """
    # Other users' lines don't exist for them (404)
    found = get_object_or_404(
        ImportLine.objects.select_related("batch"), pk=pk, batch__user=request.user
    )
    batch = found.batch
    if batch.state != Import.State.PREVIEW:
        return _back_to_page(request)
    error = ""
    if "choice" in request.POST:
        rules.set_choice(found, request.POST["choice"])
    if "watched" in request.POST:
        # A hidden "0" comes before the checkbox's "1": the last value wins
        rules.set_watched(found, request.POST.getlist("watched")[-1] == "1")
    if "follow" in request.POST:
        rules.set_follow(found, request.POST.getlist("follow")[-1] == "1")
    if "query" in request.POST:
        try:
            rules.search_again(found, request.POST["query"], request.user.effective_tmdb_language)
        except tmdb.TMDBError as e:
            error = _tmdb_error(e)
    if not _is_htmx(request):
        if error:
            messages.error(request, error)
        return _back_to_page(request, f"#line-{found.pk}")
    lines, summary = rules.preview(request.user, batch, [found])
    context = {"batch": batch, "line": lines[0], "summary": summary, "line_error": error}
    response = render(request, "imports/_line_response.html", context)
    patch_vary_headers(response, ["HX-Request"])
    return response


@require_POST
def start(request):
    """Preview → import the lines."""
    batch = get_object_or_404(Import, user=request.user)
    rules.start(request.user, batch)
    return _back_to_page(request)


@require_POST
def discard(request):
    """Cancel the import, or "New import" after it is done: delete it with its lines.

    Titles that were already imported stay.
    """
    Import.objects.filter(user=request.user).delete()
    return _back_to_page(request)
