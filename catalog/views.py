import logging
from urllib.parse import urlencode

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
    """A list's titles. Filters come from the URL (?status=unwatched&type=movie)."""
    user_list = _user_list(request, pk)
    return _render_list(request, user_list, full_page=not _is_htmx_fragment_request(request))


# Filter values in the URL; the first one of each is the default ("all")
LIST_STATUS_FILTERS = ("all", "unwatched", "watched")
LIST_TYPE_FILTERS = ("all", MediaType.MOVIE, MediaType.TV)


def _list_filters(request) -> dict:
    """Current filters from the query string; unknown values fall back to "all".

    Also read on POST (layout, watched, remove), whose form actions keep the query string,
    so the list keeps its filters after an action.
    """
    status = request.GET.get("status", "all")
    media_type = request.GET.get("type", "all")
    return {
        "status": status if status in LIST_STATUS_FILTERS else "all",
        "type": media_type if media_type in LIST_TYPE_FILTERS else "all",
    }


def _filter_query(filters: dict) -> str:
    """'?status=…&type=…' without default values ('' if nothing is filtered)."""
    params = {key: value for key, value in filters.items() if value != "all"}
    return f"?{urlencode(params)}" if params else ""


def _list_context(request, user_list: UserList) -> dict:
    filters = _list_filters(request)
    all_items = list(user_list.items.select_related("title"))
    titles = [item.title for item in all_items]
    translations = services.best_translations(titles, request.user.effective_tmdb_language)
    watched = set(
        WatchedMovie.objects.filter(user=request.user, title__in=titles).values_list(
            "title_id", flat=True
        )
    )
    for item in all_items:
        item.translation = translations.get(item.title_id)
        item.watched = item.title_id in watched

    # Lists are small, so filtering in Python is simple and fast enough.
    # Shows count as unwatched until episode tracking exists (milestone 4).
    items = [
        item
        for item in all_items
        if (filters["type"] == "all" or item.title.media_type == filters["type"])
        and (filters["status"] == "all" or item.watched == (filters["status"] == "watched"))
    ]
    query = _filter_query(filters)
    return {
        "list": user_list,
        "items": items,
        "has_items": bool(all_items),
        "filters": filters,
        "filter_query": query,
        "status_filters": [
            ("all", _("All"), _filter_query({**filters, "status": "all"})),
            ("unwatched", _("Unwatched"), _filter_query({**filters, "status": "unwatched"})),
            ("watched", _("Watched"), _filter_query({**filters, "status": "watched"})),
        ],
        "type_filters": [
            ("all", _("All"), _filter_query({**filters, "type": "all"})),
            (MediaType.MOVIE, _("Movies"), _filter_query({**filters, "type": MediaType.MOVIE})),
            (MediaType.TV, _("TV shows"), _filter_query({**filters, "type": MediaType.TV})),
        ],
        "layouts": User.ListLayout,
    }


def _render_list(request, user_list: UserList, *, full_page: bool):
    template = "catalog/list_detail.html"
    if not full_page:
        template += "#list-content"
    response = render(request, template, _list_context(request, user_list))
    patch_vary_headers(response, ["HX-Request"])
    return response


def _list_response(request, user_list: UserList):
    """After an action on the list page: the updated content (htmx) or back to the list."""
    if _is_htmx_fragment_request(request):
        return _render_list(request, user_list, full_page=False)
    return redirect(user_list.get_absolute_url() + _filter_query(_list_filters(request)))


def _item_response(request, user_list: UserList, item_pk: int):
    """After an action on one entry: update as little as possible (htmx).

    Replacing the whole list would rebuild every poster image, which flickers. So:
    - entry still shown: only its watched button (and the compact view's "watched" text)
    - entry gone (removed, or no longer matching the filter): only this entry disappears
    - nothing left to show: the whole content, with the "empty" message
    """
    if not _is_htmx_fragment_request(request):
        return redirect(user_list.get_absolute_url() + _filter_query(_list_filters(request)))
    context = _list_context(request, user_list)
    item = next((item for item in context["items"] if item.pk == item_pk), None)
    if not context["items"]:
        response = _render_list(request, user_list, full_page=False)
        response["HX-Retarget"] = "#list-content"
        response["HX-Reswap"] = "innerHTML"
    elif item is None:
        response = HttpResponse("")
        response["HX-Retarget"] = "closest li"
        response["HX-Reswap"] = "outerHTML"
    else:
        context.update(
            item=item,
            name=item.translation.name if item.translation else item.title.original_title,
            corner=request.user.list_layout == User.ListLayout.GRID,
        )
        response = render(request, "catalog/_watched_toggle_response.html", context)
    patch_vary_headers(response, ["HX-Request"])
    return response


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
    return _list_response(request, user_list)


@require_POST
def list_item_remove(request, pk, item_pk):
    user_list = _user_list(request, pk)
    get_object_or_404(user_list.items, pk=item_pk).delete()
    return _item_response(request, user_list, item_pk)


@require_POST
def list_item_watched(request, pk, item_pk):
    """Watched button on a list entry: `watched` present = mark (today), missing = undo.

    Only movies for now; shows get "next episode watched" with milestone 4.
    """
    user_list = _user_list(request, pk)
    item = get_object_or_404(
        user_list.items.select_related("title"), pk=item_pk, title__media_type=MediaType.MOVIE
    )
    if request.POST.get("watched"):
        # Already watched: keep the date that may have been set on the detail page
        if not WatchedMovie.objects.filter(user=request.user, title=item.title).exists():
            list_rules.mark_watched(request.user, item.title)
    else:
        list_rules.unmark_watched(request.user, item.title)
    return _item_response(request, user_list, item.pk)


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
