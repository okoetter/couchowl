import logging

from django.conf import settings
from django.contrib import messages
from django.db.models import Count
from django.db.models.functions import Lower
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import patch_cache_control, patch_vary_headers
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from accounts.models import User
from accounts.throttle import hit

from . import lists as list_rules
from . import posters, services, tmdb
from .forms import ListForm, WatchedDateForm
from .models import MediaType, Title, TitleTranslation, UserList, WatchedMovie

logger = logging.getLogger(__name__)


def _is_htmx_fragment_request(request) -> bool:
    """htmx asks for a page fragment; a history restore (back button) needs the full page."""
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


@require_GET
def search(request):
    """Search page. Live search (htmx) only gets the results fragment.

    Also works without JavaScript: the form submits ?q=… and gets the full page.
    """
    query = services.normalize_query(request.GET.get("q", ""))
    results, error = [], None
    if len(query) >= services.MIN_QUERY_LENGTH:
        if not hit(f"search:{request.user.pk}", settings.SEARCH_RATE_LIMIT, 60):
            error = _("Too many searches in a short time. Please wait a moment.")
        else:
            try:
                results = services.search(query, request.user.effective_tmdb_language)
            except tmdb.TMDBNotConfigured:
                error = _("Search is not available: the administrator has not set up TMDB yet.")
            except tmdb.TMDBError:
                logger.exception("TMDB search failed")
                error = _("TMDB can't be reached right now. Please try again later.")

    watched = list_rules.watched_movie_ids(
        request.user, (r.tmdb_id for r in results if r.media_type == MediaType.MOVIE)
    )
    context = {
        "query": query,
        "results": results,
        "watched": watched,
        "error": error,
        "min_query_length": services.MIN_QUERY_LENGTH,
    }
    template = "catalog/search.html"
    if _is_htmx_fragment_request(request):
        template += "#results"
    response = render(request, template, context)
    # Browsers must not mix up cached fragment and full page (e.g. on "back")
    patch_vary_headers(response, ["HX-Request"])
    return response


@require_GET
def poster(request, size, filename):
    """Serve a TMDB poster from the local cache (downloaded on first request)."""
    if not posters.is_valid(size, filename):
        raise Http404
    try:
        path = posters.cached_poster(size, filename)
    except tmdb.TMDBNotFound:
        raise Http404 from None
    except tmdb.TMDBError:
        logger.warning("Could not load poster %s/%s from TMDB", size, filename, exc_info=True)
        return HttpResponse(status=502)

    response = FileResponse(path.open("rb"), content_type=posters.content_type(filename))
    # The file behind a TMDB path never changes. "private": only for logged-in users.
    patch_cache_control(response, private=True, max_age=365 * 24 * 3600, immutable=True)
    return response


# --- Lists ---------------------------------------------------------------------------------


def _user_list(request, pk) -> UserList:
    """A list of the logged-in user. Other users' lists don't exist for them (404)."""
    return get_object_or_404(UserList, pk=pk, user=request.user)


def lists(request):
    """All lists of the user, plus a form to create a new one."""
    if request.method == "POST":
        form = ListForm(request.POST, user=request.user)
        if form.is_valid():
            user_list = form.save()
            messages.success(request, _("List “%(name)s” created.") % {"name": user_list})
            return redirect(user_list)
    else:
        form = ListForm(user=request.user)
    # Meta.ordering is ignored in queries with aggregates (Count), so sort explicitly
    user_lists = request.user.lists.annotate(item_count=Count("items")).order_by(Lower("name"))
    return render(request, "catalog/lists.html", {"lists": user_lists, "form": form})


@require_GET
def list_detail(request, pk):
    user_list = _user_list(request, pk)
    return render(request, "catalog/list_detail.html", _list_context(request, user_list))


def _list_context(request, user_list: UserList) -> dict:
    items = list(user_list.items.select_related("title"))
    titles = [item.title for item in items]
    translations = services.best_translations(titles, request.user.effective_tmdb_language)
    watched = set(
        WatchedMovie.objects.filter(user=request.user, title__in=titles).values_list(
            "title_id", flat=True
        )
    )
    for item in items:
        item.translation = translations.get(item.title_id)
        item.watched = item.title_id in watched
    return {"list": user_list, "items": items, "layouts": User.ListLayout}


def list_rename(request, pk):
    user_list = _user_list(request, pk)
    if request.method == "POST":
        # Separate instance: an invalid name must not show up elsewhere on the page
        form = ListForm(request.POST, instance=_user_list(request, pk), user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("List renamed."))
            return redirect(user_list)
    else:
        form = ListForm(instance=user_list, user=request.user)
    return render(request, "catalog/list_rename.html", {"list": user_list, "form": form})


def list_delete(request, pk):
    """GET asks for confirmation, POST deletes. The titles themselves stay in the catalog."""
    user_list = _user_list(request, pk)
    if request.method == "POST":
        user_list.delete()
        messages.success(request, _("List “%(name)s” deleted.") % {"name": user_list})
        return redirect("catalog:lists")
    return render(
        request,
        "catalog/list_delete.html",
        {"list": user_list, "item_count": user_list.items.count()},
    )


@require_POST
def list_layout(request, pk):
    """Switch between poster grid and compact list (saved per user, for all lists)."""
    user_list = _user_list(request, pk)
    layout = request.POST.get("layout")
    if layout in User.ListLayout.values:
        request.user.list_layout = layout
        request.user.save(update_fields=["list_layout"])
    if _is_htmx_fragment_request(request):
        return render(
            request, "catalog/list_detail.html#list-content", _list_context(request, user_list)
        )
    return redirect(user_list)


@require_POST
def list_item_remove(request, pk, item_pk):
    user_list = _user_list(request, pk)
    item = get_object_or_404(user_list.items, pk=item_pk)
    item.delete()
    if _is_htmx_fragment_request(request):
        return render(
            request, "catalog/list_detail.html#list-content", _list_context(request, user_list)
        )
    return redirect(user_list)


# --- Movies and shows ------------------------------------------------------------------------


def _load_title(request, media_type, tmdb_id) -> tuple[TitleTranslation | None, str]:
    """(translation, "") or (None, error message). Unknown titles raise Http404."""
    try:
        translation = services.get_title(media_type, tmdb_id, request.user.effective_tmdb_language)
    except tmdb.TMDBNotFound:
        raise Http404 from None
    except tmdb.TMDBNotConfigured:
        return None, _("The administrator has not set up TMDB yet.")
    except tmdb.TMDBError:
        logger.exception("Could not load %s %s from TMDB", media_type, tmdb_id)
        return None, _("TMDB can't be reached right now. Please try again later.")
    return translation, ""


@require_GET
def title_detail(request, media_type, tmdb_id):
    """Detail page of a movie or show (loaded from TMDB if missing or outdated)."""
    translation, error = _load_title(request, media_type, tmdb_id)
    if translation is None:
        return render(request, "catalog/title_error.html", {"error": error}, status=503)
    title = translation.title
    context = {
        "title": title,
        "translation": translation,
        **_menu_context(request, media_type, tmdb_id, title),
    }
    if title.is_movie:
        context.update(_watched_context(request, title))
    return render(request, "catalog/title_detail.html", context)


def _menu_context(request, media_type, tmdb_id, title, error="") -> dict:
    return {
        "media_type": media_type,
        "tmdb_id": tmdb_id,
        "lists": list_rules.lists_for_title(request.user, title),
        "menu_error": error,
    }


def _render_menu(request, media_type, tmdb_id, title, error=""):
    context = _menu_context(request, media_type, tmdb_id, title, error)
    return render(request, "catalog/_list_menu.html", context)


@require_GET
def title_lists(request, media_type, tmdb_id):
    """The "add to list" menu (loaded when it is opened, e.g. in search results).

    Doesn't contact TMDB: a title that isn't stored yet simply isn't on any list.
    """
    title = Title.objects.filter(media_type=media_type, tmdb_id=tmdb_id).first()
    return _render_menu(request, media_type, tmdb_id, title)


@require_POST
def title_list_membership(request, media_type, tmdb_id, list_pk):
    """Checkbox in the menu: `member` present = put on the list, missing = take off."""
    user_list = _user_list(request, list_pk)
    translation, error = _load_title(request, media_type, tmdb_id)
    if translation is None:
        title = Title.objects.filter(media_type=media_type, tmdb_id=tmdb_id).first()
        return _render_menu(request, media_type, tmdb_id, title, error)
    if request.POST.get("member"):
        list_rules.add_to_list(user_list, translation.title)
    else:
        list_rules.remove_from_list(user_list, translation.title)
    return _render_menu(request, media_type, tmdb_id, translation.title)


@require_POST
def title_list_create(request, media_type, tmdb_id):
    """Menu: create a list (or use the one with that name) and put the title on it."""
    name = " ".join(request.POST.get("name", "").split())
    max_length = UserList._meta.get_field("name").max_length
    translation, error = _load_title(request, media_type, tmdb_id)
    if translation is None:
        title = Title.objects.filter(media_type=media_type, tmdb_id=tmdb_id).first()
        return _render_menu(request, media_type, tmdb_id, title, error)
    if not name or len(name) > max_length:
        error = _("Please enter a name (at most %(max)s characters).") % {"max": max_length}
        return _render_menu(request, media_type, tmdb_id, translation.title, error)
    user_list = list_rules.find_or_create_list(request.user, name)
    list_rules.add_to_list(user_list, translation.title)
    return _render_menu(request, media_type, tmdb_id, translation.title)


def _watched_context(request, movie: Title, form=None) -> dict:
    watched = WatchedMovie.objects.filter(user=request.user, title=movie).first()
    if form is None:
        initial = {}
        if watched:
            initial = {"watched_at": watched.watched_at, "unknown": watched.watched_at is None}
        form = WatchedDateForm(initial=initial)
    return {"title": movie, "watched": watched, "date_form": form}


@require_POST
def movie_watched(request, tmdb_id):
    """Mark as watched (today), change the date, or undo."""
    movie = get_object_or_404(Title, media_type=MediaType.MOVIE, tmdb_id=tmdb_id)
    action = request.POST.get("action")
    form = None
    if action == "mark":
        list_rules.mark_watched(request.user, movie)
    elif action == "unmark":
        list_rules.unmark_watched(request.user, movie)
    elif action == "date":
        form = WatchedDateForm(request.POST)
        if form.is_valid():
            date = form.cleaned_data["watched_at"]
            list_rules.mark_watched(request.user, movie, date, unknown_date=date is None)
            form = None
    else:
        return HttpResponse(status=400)

    if _is_htmx_fragment_request(request):
        context = _watched_context(request, movie, form)
        return render(request, "catalog/title_detail.html#watched", context)
    if form is not None:  # invalid date without JavaScript
        messages.error(request, " ".join(e for errors in form.errors.values() for e in errors))
    return redirect(movie)
