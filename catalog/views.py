import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db.models import Count
from django.db.models.functions import Lower
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_cache_control, patch_vary_headers
from django.utils.translation import get_language, ngettext
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from accounts.models import User
from accounts.regions import country_name
from accounts.throttle import hit

from . import lists as list_rules
from . import posters, providers, services, shows, tmdb
from .forms import ListForm, RestoreItemForm, WatchedDateForm
from .models import Episode, MediaType, Season, Title, TitleTranslation, UserList, WatchedMovie

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

    movie_ids = [r.tmdb_id for r in results if r.media_type == MediaType.MOVIE]
    show_ids = [r.tmdb_id for r in results if r.media_type == MediaType.TV]
    watched = {f"movie-{i}" for i in list_rules.watched_movie_ids(request.user, movie_ids)}
    watched |= {f"tv-{i}" for i in shows.watched_show_ids(request.user, show_ids)}
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


def _user_list(request, pk) -> UserList | list_rules.FollowedShows:
    """A list of the logged-in user. Other users' lists don't exist for them (404).

    pk "followed" is the system list "Followed shows" (computed, not stored).
    """
    if pk == list_rules.FollowedShows.pk:
        return list_rules.FollowedShows(request.user)
    return get_object_or_404(UserList, pk=pk, user=request.user)


def _editable_list(request, pk) -> UserList:
    """A list the user may rename, delete or remove entries from (not a system list)."""
    user_list = _user_list(request, pk)
    if user_list.is_system:
        raise Http404
    return user_list


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
    # The system list appears as soon as the user follows a show (unless hidden in the profile)
    followed = None
    if request.user.show_followed_list:
        followed = list_rules.FollowedShows(request.user)
        followed.item_count = followed.items.count()
    context = {"lists": user_lists, "followed": followed, "form": form}
    return render(request, "catalog/lists.html", context)


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
    progress = shows.progress(request.user, [t for t in titles if not t.is_movie])
    following = shows.followed_ids(request.user, titles)
    for item in all_items:
        item.translation = translations.get(item.title_id)
        item.following = item.title_id in following
        if item.title.is_movie:
            item.watched = item.title_id in watched
        else:
            # A show is watched when all aired episodes are (see catalog.shows)
            item.progress = progress[item.title_id]
            item.watched = item.progress.complete

    # Lists are small, so filtering in Python is simple and fast enough.
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


def _item_response(request, user_list: UserList, item_pk: int, *, toast: Episode | None = None):
    """After an action on one entry: update as little as possible (htmx).

    Replacing the whole list would rebuild every poster image, which flickers. So:
    - entry still shown: only its watched button (and the compact view's "watched" text)
    - entry gone (removed, or no longer matching the filter): only this entry disappears
    - nothing left to show: the whole content, with the "empty" message
    `toast`: an episode that was just marked; a message with "undo" is added.
    """
    if not _is_htmx_fragment_request(request):
        if toast is not None:
            messages.success(request, _("%(episode)s watched.") % {"episode": toast.code})
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
    if toast is not None:
        response.content += _toast(request, user_list, item_pk, toast).encode()
    patch_vary_headers(response, ["HX-Request"])
    return response


def _toast(request, user_list, item_pk, episode: Episode | None) -> str:
    """The "S2 E5 watched · Undo" message (htmx puts it in place by its id)."""
    context = {
        "message": _("%(code)s watched") % {"code": episode.code} if episode else "",
        "undo_url": reverse("catalog:list_item_watched", args=[user_list.pk, item_pk])
        + _filter_query(_list_filters(request)),
        "undo_fields": {"undo": episode.pk} if episode else {},
    }
    return render_to_string("catalog/_toast.html", context, request=request)


def list_rename(request, pk):
    user_list = _editable_list(request, pk)
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
    user_list = _editable_list(request, pk)
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
    """Trash button (edit mode); the message "“Heat” removed" offers "Undo"."""
    user_list = _editable_list(request, pk)
    item = get_object_or_404(user_list.items.select_related("title"), pk=item_pk)
    added_at = item.added_at
    item.delete()
    translation = services.best_translations(
        [item.title], request.user.effective_tmdb_language
    ).get(item.title_id)
    name = translation.name if translation else item.title.original_title
    message = _("“%(name)s” removed") % {"name": name}
    if not _is_htmx_fragment_request(request):
        messages.success(request, message)
    response = _item_response(request, user_list, item_pk)
    if _is_htmx_fragment_request(request):
        context = {
            "message": message,
            "undo_url": reverse("catalog:list_item_restore", args=[user_list.pk])
            + _filter_query(_list_filters(request)),
            "undo_fields": {"title": item.title_id, "added_at": added_at.isoformat()},
        }
        response.content += render_to_string(
            "catalog/_toast.html", context, request=request
        ).encode()
    return response


@require_POST
def list_item_restore(request, pk):
    """ "Undo" after removing: the entry comes back at its old place in the list."""
    user_list = _editable_list(request, pk)
    form = RestoreItemForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest()
    list_rules.restore_item(user_list, form.cleaned_data["title"], form.cleaned_data["added_at"])
    response = _list_response(request, user_list)
    if _is_htmx_fragment_request(request):
        response.content += render_to_string("catalog/_toast.html", request=request).encode()
    return response


@require_POST
def list_item_watched(request, pk, item_pk):
    """Watched button on a list entry.

    Movies: `watched` present = mark (today), missing = undo.
    Shows: mark the next episode (today) and show "S2 E5 watched · Undo";
    `undo=<episode id>` takes that back; `unwatched` marks the whole show as not watched.
    """
    user_list = _user_list(request, pk)
    item = get_object_or_404(user_list.items.select_related("title"), pk=item_pk)
    if not item.title.is_movie:
        return _show_item_watched(request, user_list, item)
    if request.POST.get("watched"):
        # Already watched: keep the date that may have been set on the detail page
        if not WatchedMovie.objects.filter(user=request.user, title=item.title).exists():
            list_rules.mark_watched(request.user, item.title)
    else:
        list_rules.unmark_watched(request.user, item.title)
    return _item_response(request, user_list, item.pk)


def _show_item_watched(request, user_list, item):
    if undo := request.POST.get("undo"):
        episode = get_object_or_404(Episode, pk=undo, season__show=item.title)
        shows.unmark_episodes(request.user, [episode])
        if not _is_htmx_fragment_request(request):
            return _list_response(request, user_list)
        # The whole content, because the entry may have left the filter in the meantime
        # ("morph" keeps the posters); the empty toast hides the message
        response = _render_list(request, user_list, full_page=False)
        response.content += _toast(request, user_list, item.pk, None).encode()
        return response
    if request.POST.get("unwatched"):
        shows.unmark_show(request.user, item.title)
        response = _item_response(request, user_list, item.pk)
        if _is_htmx_fragment_request(request):
            # An "S3 E10 watched · Undo" still shown would undo nothing any more
            response.content += _toast(request, user_list, item.pk, None).encode()
        return response
    episode = shows.watch_next(request.user, item.title)
    return _item_response(request, user_list, item.pk, toast=episode)


# --- Movies and shows ------------------------------------------------------------------------


def _load_title(request, media_type, tmdb_id) -> tuple[TitleTranslation | None, str]:
    """(translation, "") or (None, error message). Unknown titles raise Http404."""
    try:
        translation = services.get_title(
            media_type,
            tmdb_id,
            request.user.effective_tmdb_language,
            region=request.user.effective_region,
        )
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
    region = request.user.effective_region
    offers = providers.offers(title, region)
    context = {
        "title": title,
        "translation": translation,
        "offers": offers,
        # Without offers: start dates, networks (see providers.availability)
        "availability": (
            None if offers else providers.availability(title, region, timezone.localdate())
        ),
        "tmdb_link": title.tmdb_url(request.user.effective_tmdb_language),
        "region_name": country_name(region, get_language()),
        **_menu_context(request, media_type, tmdb_id, title),
    }
    if title.is_movie:
        context.update(_watched_context(request, title))
    else:
        context.update(_show_context(request, title))
        context["earlier"] = _pop_earlier_prompt(request, title)
    return render(request, "catalog/title_detail.html", context)


# "Refresh now" on detail pages: requests per user and minute (protects the TMDB quota)
REFRESH_LIMIT = 10


@require_POST
def title_refresh(request, media_type, tmdb_id):
    """Button "Refresh now": reload the title from TMDB (texts, poster, seasons, providers)."""
    url = reverse("catalog:title_detail", args=[media_type, tmdb_id])
    if not hit(f"refresh:{request.user.pk}", REFRESH_LIMIT, 60):
        messages.warning(request, _("Too many refreshes in a short time. Please wait a moment."))
        return redirect(url)
    try:
        services.fetch_title(media_type, tmdb_id, request.user.effective_tmdb_language)
    except tmdb.TMDBNotFound:
        raise Http404 from None
    except tmdb.TMDBNotConfigured:
        messages.error(request, _("The administrator has not set up TMDB yet."))
    except tmdb.TMDBError:
        logger.exception("Could not refresh %s %s from TMDB", media_type, tmdb_id)
        messages.error(request, _("TMDB can't be reached right now. Please try again later."))
    else:
        messages.success(request, _("Refreshed from TMDB."))
    return redirect(url)


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


# --- Shows: following, seasons and episodes --------------------------------------------------


def _show(tmdb_id) -> Title:
    """A stored show (actions need it stored; the detail page loads it from TMDB first)."""
    return get_object_or_404(Title, media_type=MediaType.TV, tmdb_id=tmdb_id)


def _season_anchor_url(show: Title, season: int, anchor: str = "") -> str:
    """Detail page with this season opened, scrolled to `anchor` (fallback without JS)."""
    return f"{show.get_absolute_url()}?season={season}#{anchor or f'season-{season}'}"


def _show_context(request, show: Title) -> dict:
    """Everything the seasons part of a show's detail page needs.

    Only the open season gets its episodes; the others load them when opened (htmx), so
    long-running shows with hundreds of episodes stay fast. Open is the season from
    ?season=N (also the fallback without JavaScript), else the one with the next episode.
    """
    language = request.user.effective_tmdb_language
    try:
        open_season = int(request.GET.get("season", ""))
    except ValueError:
        open_season = None
    context = _progress_context(request, show)
    next_episode = context["progress"].next_episode
    if open_season is None and next_episode is not None:
        open_season = next_episode.season.number
    seasons = shows.seasons_overview(request.user, show, language)
    for season in seasons:
        season.episode_rows = None
        if season.number == open_season:
            _add_episode_rows(request, show, season)
    return {
        **context,
        "following": shows.is_following(request.user, show),
        "seasons": seasons,
        "open_season": open_season,
    }


def _progress_context(request, show: Title) -> dict:
    """Progress line at the top: "12 of 26 episodes watched · Next: S2 E5 …"."""
    progress = shows.progress(request.user, [show])[show.pk]
    next_name = ""
    if progress.next_episode is not None:
        names = shows.episode_names([progress.next_episode], request.user.effective_tmdb_language)
        next_name = names.get(progress.next_episode.pk, "")
    return {"title": show, "progress": progress, "next_name": next_name}


def _date_form(prefix, watched_at, has_date=True) -> WatchedDateForm:
    """Date form for an episode or season. Prefixes keep the fields of many forms apart."""
    return WatchedDateForm(
        prefix=prefix,
        initial={"watched_at": watched_at, "unknown": not has_date},
    )


def _add_episode_rows(request, show: Title, season: Season, bound_forms=None) -> None:
    """Load the episodes of `season` with their date forms (`bound_forms` show errors)."""
    bound_forms = bound_forms or {}
    season.episode_rows = shows.season_episodes(
        request.user, season, request.user.effective_tmdb_language
    )
    for episode in season.episode_rows:
        prefix = f"e{season.number}-{episode.number}"
        if episode.watched:
            episode.date_form = bound_forms.get(prefix) or _date_form(
                prefix, episode.watched.watched_at, episode.watched.watched_at is not None
            )
    prefix = f"s{season.number}"
    season.date_form = bound_forms.get(prefix) or _date_form(
        prefix, season.last_watched, season.last_watched is not None
    )


def _season_context(request, show: Title, number: int, bound_forms=None) -> dict:
    season = next(
        (
            s
            for s in shows.seasons_overview(
                request.user, show, request.user.effective_tmdb_language
            )
            if s.number == number
        ),
        None,
    )
    if season is None:
        raise Http404
    _add_episode_rows(request, show, season, bound_forms)
    return {**_progress_context(request, show), "season": season}


@require_POST
def show_follow(request, tmdb_id):
    """Follow button: `following` present = follow, missing = unfollow."""
    show = _show(tmdb_id)
    shows.set_following(request.user, show, bool(request.POST.get("following")))
    if _is_htmx_fragment_request(request):
        context = {"title": show, "following": shows.is_following(request.user, show)}
        return render(request, "catalog/title_detail.html#follow", context)
    return redirect(show)


@require_GET
def season_episodes(request, tmdb_id, season):
    """Episodes of a season, loaded when the season is opened on the detail page."""
    show = _show(tmdb_id)
    if not _is_htmx_fragment_request(request):
        return redirect(_season_anchor_url(show, season))
    response = render(
        request, "catalog/_seasons.html#season-episodes", _season_context(request, show, season)
    )
    patch_vary_headers(response, ["HX-Request"])
    return response


def _date_from_form(request, prefix):
    """(date, unknown, form): a valid date form gives (date or None, unknown?, None)."""
    form = WatchedDateForm(request.POST, prefix=prefix)
    if form.is_valid():
        watched_at = form.cleaned_data["watched_at"]
        return watched_at, watched_at is None, None
    return None, False, form


@require_POST
def episode_watched(request, tmdb_id, season, episode):
    """Mark an episode as watched (today), change its date, or undo."""
    show = _show(tmdb_id)
    found = get_object_or_404(
        Episode.objects.select_related("season"),
        season__show=show,
        season__number=season,
        number=episode,
    )
    action = request.POST.get("action")
    prefix = f"e{season}-{episode}"
    form = None
    earlier = None
    if action == "mark":
        # Not aired yet: nothing happens
        if shows.mark_episode(request.user, found):
            earlier = _earlier_prompt(request, show, found.season, found)
    elif action == "unmark":
        shows.unmark_episodes(request.user, [found])
    elif action == "date":
        watched_at, unknown, form = _date_from_form(request, prefix)
        if form is None:
            shows.mark_episode(request.user, found, watched_at, unknown_date=unknown)
    else:
        return HttpResponse(status=400)

    if _is_htmx_fragment_request(request):
        context = _season_context(request, show, season, {prefix: form} if form else None)
        context["episode"] = next(e for e in context["season"].episode_rows if e.pk == found.pk)
        context["earlier"] = earlier
        return render(request, "catalog/_episode_response.html", context)
    if form is not None:
        messages.error(request, " ".join(e for errors in form.errors.values() for e in errors))
    _remember_earlier_prompt(request, earlier)
    return redirect(_season_anchor_url(show, season, f"episode-{season}-{episode}"))


@require_POST
def show_unwatched(request, tmdb_id):
    """Mark the whole show as not watched (asks first, see the progress line).

    htmx gets the seasons (morphed, so unchanged parts stay) and the progress line.
    """
    show = _show(tmdb_id)
    shows.unmark_show(request.user, show)
    if not _is_htmx_fragment_request(request):
        return redirect(show)
    context = {**_show_context(request, show), "earlier": None}
    return render(request, "catalog/_show_unwatched_response.html", context)


@require_POST
def season_watched(request, tmdb_id, season):
    """Mark all aired episodes of a season (watched ones keep their date), set one date
    for all of them, or undo the whole season."""
    show = _show(tmdb_id)
    found = get_object_or_404(Season, show=show, number=season)
    action = request.POST.get("action")
    prefix = f"s{season}"
    form = None
    earlier = None
    if action == "mark":
        if shows.mark_season(request.user, found):
            earlier = _earlier_prompt(request, show, found)
    elif action == "unmark":
        shows.unmark_season(request.user, found)
    elif action == "date":
        watched_at, unknown, form = _date_from_form(request, prefix)
        if form is None:
            shows.mark_season(
                request.user, found, watched_at, unknown_date=unknown, keep_existing=False
            )
    else:
        return HttpResponse(status=400)

    if _is_htmx_fragment_request(request):
        context = _season_context(request, show, season, {prefix: form} if form else None)
        context["earlier"] = earlier
        return render(request, "catalog/_season_response.html", context)
    if form is not None:
        messages.error(request, " ".join(e for errors in form.errors.values() for e in errors))
    _remember_earlier_prompt(request, earlier)
    return redirect(_season_anchor_url(show, season))


# --- "Mark earlier episodes too?" ------------------------------------------------------------
#
# After marking an episode (or season) on the detail page, a message asks whether the
# earlier unwatched episodes should be marked as well, with the date "unknown": you didn't
# watch them today. It stays until answered or replaced by the next action (no timeout).


def _earlier_prompt(request, show: Title, season: Season, episode: Episode | None = None):
    """Context for the question, or None if nothing earlier is unwatched."""
    earlier = shows.unwatched_before(request.user, season, episode)
    if not earlier:
        return None
    in_season = sum(1 for e in earlier if e.season_id == season.pk)
    return {
        "show": show,
        "marked": episode.code if episode else shows.default_season_name(season),
        "season": season.number,
        "episode": episode.number if episode else "",
        "count": len(earlier),
        # "Only season 3" only makes sense if older seasons have gaps too
        "in_season": in_season if 0 < in_season < len(earlier) else 0,
    }


def _remember_earlier_prompt(request, earlier) -> None:
    """Without JavaScript the question appears on the detail page after the redirect."""
    if earlier is not None:
        request.session["earlier_prompt"] = {
            "show": earlier["show"].pk,
            "season": earlier["season"],
            "episode": earlier["episode"],
        }


def _pop_earlier_prompt(request, show: Title):
    stored = request.session.pop("earlier_prompt", None)
    if not stored or stored.get("show") != show.pk:
        return None
    season = Season.objects.filter(show=show, number=stored["season"]).first()
    if season is None:
        return None
    episode = None
    if stored["episode"] != "":
        episode = season.episodes.select_related("season").filter(number=stored["episode"]).first()
        if episode is None:
            return None
    return _earlier_prompt(request, show, season, episode)


@require_POST
def watched_earlier(request, tmdb_id):
    """Answer to the question: mark the earlier unwatched episodes (date unknown), either
    of the whole show (`scope=all`) or only of the same season; or `undo=<ids>`.

    htmx gets the changed seasons and the progress line by their ids, plus a message.
    """
    show = _show(tmdb_id)
    if undo := request.POST.get("undo"):
        ids = [int(pk) for pk in undo.split(",") if pk.isdigit()]
        episodes = list(
            Episode.objects.filter(pk__in=ids, season__show=show).select_related("season")
        )
        shows.unmark_episodes(request.user, episodes)
        if not _is_htmx_fragment_request(request):
            return redirect(show)
        return _earlier_response(request, show, episodes, toast=None)

    season_number, episode_number = request.POST.get("season", ""), request.POST.get("episode", "")
    if not season_number.isdigit() or not (episode_number.isdigit() or episode_number == ""):
        return HttpResponse(status=400)
    season = get_object_or_404(Season, show=show, number=season_number)
    episode = None
    if episode_number:
        episode = get_object_or_404(
            Episode.objects.select_related("season"), season=season, number=episode_number
        )
    episodes = shows.unwatched_before(request.user, season, episode)
    if request.POST.get("scope") != "all":
        episodes = [e for e in episodes if e.season_id == season.pk]
    marked = shows.mark_episodes(request.user, episodes, unknown_date=True, keep_existing=True)
    message = ngettext(
        "%(count)s episode marked as watched.", "%(count)s episodes marked as watched.", len(marked)
    ) % {"count": len(marked)}
    if not _is_htmx_fragment_request(request):
        messages.success(request, message)
        return redirect(_season_anchor_url(show, season.number))
    toast = {"message": message, "undo": ",".join(str(e.pk) for e in marked)} if marked else None
    return _earlier_response(request, show, marked, toast=toast)


def _earlier_response(request, show: Title, episodes, toast):
    """The seasons of `episodes` (button, info, episodes) and the progress line, by id."""
    numbers = {episode.season.number for episode in episodes}
    seasons = [
        season
        for season in shows.seasons_overview(
            request.user, show, request.user.effective_tmdb_language
        )
        if season.number in numbers
    ]
    for season in seasons:
        _add_episode_rows(request, show, season)
    context = {**_progress_context(request, show), "seasons": seasons, "toast": toast}
    response = render(request, "catalog/_earlier_response.html", context)
    patch_vary_headers(response, ["HX-Request"])
    return response
