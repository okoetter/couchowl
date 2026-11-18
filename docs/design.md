# Design decisions

Why Couch Owl works the way it does. This document describes the current state, ordered by
topic; each section gives the rules and the reasons behind them, and alternatives that were
considered and rejected. When a decision changes, the section is updated in the same
change. For what's planned next see [ROADMAP.md](ROADMAP.md); for setup and operation see
[deployment.md](deployment.md) and [administration.md](administration.md).

## Goals

- A self-hosted watchlist for movies and TV shows for a household or a small group of
  friends: invite-only, reachable from the internet, installable on phones.
- Small: one Docker container, SQLite, comfortable on a NAS with 2 GB of RAM.
- Private: browsers never contact third parties. All data from TMDB goes through the
  server.
- Plain, server-rendered pages that also work without JavaScript where reasonable.

## Product

### Accounts

- **Invite-only.** Admins create one-time invitation links in the Django admin. After
  saving, the link is shown right away for copying; with e-mail configured and an address
  entered, it is also sent automatically (and can be resent via an admin action).
  Validity: `INVITATION_EXPIRY_DAYS` (default 7). Invitation e-mails use the inviting
  admin's language.
- **Every page requires login** (Django's `LoginRequiredMiddleware`). Public are only
  login, registration by invitation, password reset, the About page, the health check and
  the PWA manifest.
- **E-mail is optional.** The address in the profile is optional but unique if set
  (otherwise a reset mail could go to several accounts). Without `EMAIL_URL`, "Forgot
  password" is replaced by "ask your administrator"; admins create reset links via an
  admin action and pass them on any way they like. Reset links are valid for
  `PASSWORD_RESET_TIMEOUT_HOURS` (default 24). The reset form never reveals whether an
  address exists.
- **E-mail configuration lives in environment variables**, not in the admin: secrets stay
  out of the database, it works before the first login, and it's the Docker convention.
  `EMAIL_URL` is converted to Django 6.1's `MAILERS` setting (`config/mail.py`).
- **Logins last until `SESSION_DAYS` (default 90) without a visit.** Django moves a
  session's expiry only when its data changes, so its default (14 days, not renewed) logged
  daily users out every two weeks, annoying in the phone app. `SessionRenewalMiddleware`
  (`accounts/middleware.py`) changes the session at most once a day, which saves it with a
  new expiry and cookie. `SESSION_SAVE_EVERY_REQUEST` would do the same with a database
  write per request. 90 days because a watchlist is low-risk; logging out ends a session,
  changing the password ends all other sessions of that user (Django), deactivating a user
  ends all of theirs. Rejected: a "Stay logged in" checkbox (in the app one always wants
  that; on shared devices, log out) and a per-user setting (effort for an edge case).
- **Brute-force protection** with django-axes: the combination of user name **and** client
  address is locked after 5 failures for 60 minutes. Locking by address alone would lock
  everyone out behind a reverse proxy without a correct client address.
- **Rate limits** (Django's cache, a file cache in `DATA_DIR/cache` so all gunicorn
  processes share it): "Forgot password" 5 per hour and address, live search 60 per
  minute and user, "Refresh now" 10 per minute and user, "Refresh all" once per 5 minutes
  and user, password attempts for "Reset my data" 5 per hour and user.
- **"Reset my data"** (`/accounts/profile/reset/`, `catalog/reset.py`): deletes all of the
  user's lists, watched movies and episodes, follows, show statuses and a batch import, to
  start over, e.g. after a failed import. Account, password, profile settings and TMDB
  data (shared by all users) stay. Show statuses go too, so the first mark afterwards
  follows a show again.
  The link sits at the bottom of the profile in a separate danger zone (rarely needed, a
  misclick would be fatal). The page first shows what will be lost ("4 lists, 312 watched
  movies, …"), says clearly that this can't be undone (the nightly database copy holds all
  users, so one user can't be restored from it) and asks for the password, so a misclick
  or an unattended logged-in device isn't enough. The password attempts are rate-limited
  because a stolen session could otherwise be used to guess the password.

### Lists

- Any number of private lists per user, each holding movies **and** shows mixed. Names are
  unique per user regardless of case; lists are sorted alphabetically (drag-and-drop
  ordering is in the backlog), entries newest first.
- **The first list creates itself:** without any list, the "Add to list" menu offers
  "Watchlist", created on the first click. It's an ordinary list afterwards. The Lists page
  never creates it, otherwise a deleted watchlist would come right back.
- Adding works from detail pages and with a "+" on every search result. The menu shows
  all lists as checkboxes plus a "New list" field; an existing name (any case) reuses that
  list. In search, the menu is loaded on every opening, so it's always current.
- **View:** poster grid or compact list, one choice per user for all lists
  (`User.list_layout`). **Filters** "All / Unwatched / Watched" and "All / Movies / Shows"
  live in the URL (bookmarkable, back button works) and aren't saved; every list starts
  at "All". Actions keep the filter, so a title marked under "Unwatched" disappears.
- **Watched button in lists:** one round button per entry, on the poster (grid) or at
  the end of the row (compact). For movies it toggles watched with today's date (an existing date is kept).
  For shows it is the same round check and marks the next episode, followed by a toast
  "S2 E5 watched · Undo". The text names that episode and, once started, a bar shows the
  progress: compact "Next: S1 E3" and the dashboard's progress bar ("12/25"); grid
  "▶ S1 E3" below the title (never broken; screen readers say "Next:") and a thin bar
  along the bottom of the poster. Earlier shows had a wider pill ("12/25", on hover
  "S1 E3"): on narrow phones it left little room for the text (compact) and covered the
  poster (grid), and two different buttons (check and pill) were confusing.
  A completely watched show shows a check mark like a watched movie; clicking it marks
  the whole show as not watched after asking (a misclick would delete all dates).
  Earlier this check couldn't be clicked, so undoing a show marked by mistake (e.g. by an
  import) took one click and one question per season on the show page.
  Unwatched buttons in the grid (movies and shows) only appear on hover, focus or touch
  devices, to keep the grid calm; the bar and "▶ S1 E3" show a show's progress anyway.
- **Followed shows are marked in lists** with a bell (the icon of the Follow button on the
  show page): after the name (compact) or in the top left corner of the poster (grid),
  only for display; following and unfollowing stay on
  the show page. Not in the system list "Followed shows", where every show has it.
- **Removing titles: edit mode.** "Edit" next to the layout toggle swaps every watched
  button for a red trash button (same place, both views) and shows a hint that watched
  data stays; "Done" ends it. Filters and the layout toggle keep the mode. It is only a
  class on `#list-content` (Alpine), whose content htmx replaces; no request, no URL
  parameter. Earlier each compact row had a "×" next to the check: two buttons per row
  took room from the text and it wasn't clear which one did what; the grid had no way to
  remove at all. Without JavaScript nothing can be removed from a list (like the toasts).
  Not in "Followed shows" (unfollow on the show page).
  A tap removes right away; the toast "“Heat” removed · Undo" brings the entry back with
  its old date, so at its old place (the form carries title and date as hidden fields).
  Rejected: collecting removals and saving them with "Done": leaving the page without
  "Done" would lose them, and filters reload the content from the server, so the marks
  would have to be kept and reapplied in JavaScript.
- **System list "Followed shows"** (`/lists/followed/`): computed, not stored; appears as
  soon as the user follows a show; same view as other lists without rename, delete,
  remove and type filter; most recently followed first; can be hidden in the profile
  (`User.show_followed_list`, default on).
- Deleting a list asks for confirmation. **Watched data is independent of lists and
  follows:** removing a title from a list, deleting a list or unfollowing a show keeps what
  was watched and when.
- Rejected for now: multi-select with bulk actions (the watched button covers the common
  case; phones would need a selection mode). Reconsider when lists get large, e.g. after
  an import.

### Watched state and dates

- Movies, single episodes and whole seasons can be marked as watched. Only the **last**
  date is stored (marking again overwrites it, no viewing history); unmarking removes it.
  The date is a day (no time), never in the future, and can be "unknown" (`watched_at`
  empty, still watched). Marking stores today; clicking the date opens a form to change
  it (works without JavaScript via `<details>`). The date input is the browser's own;
  a JavaScript calendar was rejected (worse on phones, one more library).
- **Only aired episodes** (air date today or earlier) can be marked; upcoming ones show
  their date and a dashed circle.
- **Seasons:** marking a season marks all its aired episodes; already watched ones keep
  their date. A season shows the date of its last watched episode; once complete, its date
  can be changed for all its episodes. Unmarking a whole season asks first (a misclick
  would delete all dates).
- **A whole show** can be marked as not watched: "Mark all as not watched" under the
  progress line of the show page (as soon as one episode is watched, so it also works
  after a new episode has aired) and the check mark of a completely watched show in
  lists. Both ask first. Specials go too; following, lists and the show's status stay
  (like unmarking a season), so marking episodes again later doesn't follow it again.
  The button is small: it's rarely needed and shouldn't compete with marking episodes.
- **A show counts as watched when all aired episodes are watched**, specials ("season 0")
  excluded. A new episode makes it unwatched again.
- **The next episode** is the first unwatched, aired episode, specials excluded. Lists and
  the dashboard use the same rule.
- **"Mark earlier episodes too?"** When marking an episode or season on the show page
  leaves unwatched aired episodes before it, a prompt asks: "S3 E5 watched. 12 earlier
  episodes are still unwatched." with [Only season 3 (4)] [All (12)] [No] ("Only season…"
  only if older seasons have gaps too). It marks first and asks afterwards (no modal
  before: people who skip episodes on purpose shouldn't be stopped every time). The prompt
  has no timeout; earlier episodes get the date "unknown". Lists and the dashboard never
  ask, they always mark the next episode.
- Episode descriptions are collapsed (spoilers). Dates are formatted for the user's region.

### Following, dashboard and "Upcoming"

- **"Follow" means "belongs on my dashboard"**, for both "Continue watching" and
  announcements. The button says "Follow" / "Following" (German "Folgen" / "Gefolgt", not
  "verfolgen", which sounds like chasing).
- **The first mark on a show follows it automatically**, but only the very first time
  (while `UserSeries.status` is still empty); after a deliberate unfollow, marking doesn't
  follow again. Rejected: a separate "Hide" button and "Unfollow" on dashboard cards.
- **Unfollowing never happens automatically**, only by the user. Ended or cancelled shows
  stay followed: nobody knows whether a new season comes after all.
- **The dashboard never asks TMDB**; it only shows what's in the database.
- **Continue watching:** followed shows with status "watching" that have at least one
  watched episode and a next episode; most recently watched first. A check button marks
  the next episode (today) with "Undo"; only the card's text is replaced (the poster must
  not flicker). Caught-up shows whose current season is still airing stay as a "waiting"
  card with the next air date ("in 3 days") instead of the button, after the watchable
  ones. Without a known date, or when the next season hasn't started, the card disappears;
  a season start is an announcement.
- **Announcements:** seasons (no specials) of followed shows starting between today and
  `ANNOUNCEMENT_MONTHS` months ahead (default 3; months because that's how people think
  about it), earliest first. A season starts with its first episode; TMDB's season date
  only counts when no episode has a date (they sometimes differ by a day). Each row names
  the networks and the subscription/free streaming providers of the user's region
  (variants of an already named provider are dropped: "Netflix Standard with Ads" after
  "Netflix", but "ZDFneo" after "ZDF" stays).
- **"Upcoming" page:** all known season starts of followed shows without a time limit,
  plus the next episode of seasons currently airing, grouped by month. "Refresh all"
  reloads the user's followed shows (ended and cancelled ones excluded) in the request.

### Search, ratings and streaming providers

- **Search results aren't stored**; TMDB's response is cached for an hour per query and
  language. Titles enter the database only when needed (detail page, list). Results show
  title, type, year, poster, original title if different, rating and watched state, but
  no description (the search API has no language fallback; the list stays compact).
- **Ordering:** exact title matches first (translated or original title, comparing only
  letters and digits: case, accents, spaces and punctuation don't count, so
  "Der Hobbit - Eine unerwartete Reise" matches "Der Hobbit: Eine unerwartete Reise" and
  "Spiderman" matches "Spider-Man"; titles made of punctuation only, like "?", are compared
  as they are), newest first among them; then everything else in TMDB's order.
  TMDB ranks heavily by popularity ("Dark" was fourth when searching "dark"). Sorting
  everything by year was rejected: unknown new titles would push out the known ones.
  The live search waits 300 ms after the last keystroke.
- **TMDB ratings** ("★ 8.4") in search, lists and on detail pages (with the number of
  votes). Overviews need at least 10 votes (`MIN_VOTES`; "10.0 from 2 votes" says little).
  Own ratings were dropped (not needed).
- **Streaming providers** per region on detail pages ("Available in Germany": subscription,
  free incl. with ads, rent, buy), with "Source: JustWatch" and a link to all offers on
  TMDB. They come with the detail request (`append_to_response=watch/providers`), which
  returns all ~130 regions; only the regions of our users plus `DEFAULT_REGION` are
  stored, as a JSON field `Title.watch_providers` (always read with the title, never
  queried across titles, so no separate table). If the user's region is missing (e.g.
  after changing it), the detail page reloads the title.
  The groups (only those with providers) are split by a thin line, with the label at the
  first row of logos: with many providers (e.g. "Dunkirk") the wrapped logos otherwise
  looked like the next group. Rejected: the label as a heading above the logos (just as
  clear, but noticeably taller, since the label column hardly costs logos per row).
- TMDB statuses are translated ("Ended" → "Beendet").

### Batch import

- **Why:** without it, moving to Couch Owl means entering a whole watch history by hand.
  The source is a plain list of titles (notes, a spreadsheet), one per line, optionally
  with the year (`Dark (2017)`, `Dark 2017`); bullets (`-`, `*`, `•`, `1.`, `1)`) and
  empty lines are ignored, at most 500 lines.
  Rejected: importing exports of other apps (JustWatch, Trakt, TV Time, Letterboxd);
  their titles can be pasted like any other list.
- **Years:** `(2017)` in parentheses is always a year. A trailing number without
  parentheses is ambiguous ("Wonder Woman 1984", "Blade Runner 2049", "1917"): it is not
  a year when it's the whole line or lies in the future, and when "title without the
  number + year" finds no exact match, the whole line is searched again. The year must
  match exactly; one year off (festival vs. cinema release) makes the line ambiguous
  with the right candidate on top. Rejected: ±1 tolerance (silently matches remakes).
- **Tolerant titles:** pasted lists rarely use TMDB's exact punctuation, so the
  comparison ignores it (see search ordering); without that, many correct lines needed a
  choice. Titles differing only in punctuation ("Up", "Up!") make the line ambiguous.
  Rejected: typo tolerance (edit distance; "Dark" vs. "Bark"), "&" = "and"/"und"
  (depends on the language), ignoring articles ("The Batman" vs. "Batman") and roman
  numerals ("Rocky II" = "Rocky 2"): each would match different titles silently, while
  an ambiguous line costs one click.
- **Paste → preview → import**, all on page `/import/` (linked from the lists overview, a
  list's menu ("Import" preselects the list), the empty states of lists, and the empty
  "Continue watching" as long as the user has no data at all; not hidden in the profile).
  The dashboard hint disappears once there is anything: "Continue watching" is also empty
  for people who only track movies or are between shows, and a permanent import hint on
  the start page would be noise. Every line shows its state,
  problem lines first: ambiguous (the top 5 candidates with poster, year and type to
  choose from), not found (search again or skip), matched (preselected, changeable),
  already there or duplicate (skipped).
  - **Matched:** exactly one result matches the title exactly (translated or original
    title, same comparison as search ordering), and the year if one is given.
  - **Ambiguous:** several exact matches, no exact match among the results, or the year
    doesn't match. **Not found:** no results at all.
  - **Duplicate:** resolves to the same title as an earlier line. Two lines switched to
    the same title in the preview are merged during the import (counted as duplicate):
    the earlier line is imported, marked as watched or followed if any of them is.
  - **Already there:** importing the line would change nothing (on the target list or no
    list chosen, already watched or not marked as watched, already followed or "follow"
    off). "Only already on the list" would be wrong: importing a watch history into the
    watchlist must still mark titles that are on it as watched. Recomputed whenever the
    line changes.
  - **Every change in the preview is saved right away** (choosing a candidate, the
    watched and follow switches, searching again) by a small htmx request that
    re-renders only that line. Rejected: one big form at the end (500 lines × 3 fields
    exceed Django's `DATA_UPLOAD_MAX_NUMBER_FIELDS` of 1000, and the choices would be
    lost when the page is left, which the design promises to survive). Every line can be
    searched again or skipped; matched lines keep their candidates behind "Change". The
    updated line is merged with Idiomorph (posters stay); other lines keep their state
    label until the page is reloaded (e.g. a line that becomes a duplicate of the
    changed one), the import itself always uses the current state.
  - Ambiguous lines without a choice are skipped on import and end up in the result's
    list to copy; a notice counts them before ("3 lines still need a choice").
  Rejected: asking about each ambiguous title one by one (ambiguity is common: "Dark" is
  a movie and a show; slow with long lists).
- **Options** (on the paste form): target list (existing, new or none; preselected when
  opened from a list), watched yes/no and "Follow imported shows" as defaults, each with
  a per-line switch in the preview (mixed lists in one pass). **Imported watched marks always
  get the date "unknown"** (today would distort "Continue watching" and any history; a
  common date for a whole history would be just as wrong); dates are set afterwards on
  the detail pages. A form where neither a list, "watched" nor "follow" is chosen is
  rejected, since the import would change nothing. A new list is created when the import
  starts, not on the paste form, so a cancelled import leaves no empty list behind; the
  target is stored by name, so a list deleted in the meantime comes back.
- **Following is decided per show.** "Follow imported shows" on the paste form is off by
  default and only presets the "Follow" switch, which the preview shows next to
  "Watched" once a line's choice is a show. A watch history mixes running shows (worth
  following) and ended ones; the earlier plan, one checkbox for all shows and a second
  run for those that shouldn't be followed, was clumsy for exactly that normal case.
  A switched-on line follows the show even if it is ended, cancelled or was unfollowed
  before. Help text: "Can be changed per show before importing. Also shows you
  unfollowed. Followed shows appear on the dashboard." Following is undone with one
  click, unlike lost dates, so "nothing existing is changed" doesn't need to cover it.
  For watched shows the switch decides instead of the automatic follow on the first mark
  (the import marks episodes without `_start_watching` following the show, but sets the
  status to "watching", so a later mark doesn't follow it either).
  Rejected: leaving shows with an existing `UserSeries` alone (an exception the UI would
  have to explain); a smart default (follow running, not ended shows), because the search
  doesn't return a show's status and asking TMDB per show would slow the search phase
  down; a "you unfollowed this" note per line (too much in the preview).
- **Shows are either watched completely or not started.** "Watched" marks all aired
  episodes outside of specials (season 0, consistent with when a show counts as watched)
  with an unknown date, keeping existing dates. Partly watched shows are marked
  afterwards on the show page: marking the last watched episode offers "Mark earlier
  episodes too?". Rejected: a line syntax like `Breaking Bad: S3E5` (few shows are in
  progress at once; the existing prompt is enough).
- **Nothing existing is changed:** list entries stay, watched dates of movies and
  episodes are kept, the same title twice is imported once. Each line is imported in its
  own transaction (never half a line).
- **Processed in chunks** of about 10 lines via htmx with a progress bar, for both the
  analysis (one search per line) and the import (loading each title with its seasons):
  an element with `hx-trigger="load"` posts the next step, each response returns the
  element again with the new progress, the last one redirects. The import and its lines
  are stored in the database (models `Import` and `ImportLine` in their own app
  `imports`), so the page can be left and resumed. Lines are claimed with a conditional
  update, so two open tabs don't process the same line; a claim older than two minutes
  counts as abandoned (e.g. after a worker restart). A chunk ends after 10 lines or
  10 seconds. When TMDB fails, the loop stops with "Try again" and the line stays
  pending. One import per user. The loop only runs while the page is open (said on the
  page); without JavaScript a "Continue" button runs one chunk per click. An import can
  be cancelled at any time; titles imported so far stay.
  300 lines need around 600 TMDB requests, more than fits into gunicorn's 30 s timeout.
  Rejected: one synchronous request, a background thread, a task queue with a worker
  process (one more moving part in the container).
- **Result:** imported / skipped / not found, with the lines that weren't imported in a
  read-only text field to copy. The skipped lines are listed collapsed with their reason
  (already there, same as line N, skipped by you) and a link to the title: "already
  there" is checked again when importing and can differ from the preview, and otherwise
  a missing title raises "why?". They aren't in the text field, which is for lines that
  still need something done. "New import" deletes the finished import and its lines.
  "Reset my data" deletes imports too.
- **Starting over** after a failed import: "Reset my data" in the profile (see Accounts).
  Rejected for 1.0: "Undo import" (would have to track what an import created, with edge
  cases once things change afterwards; backlog).

### Languages and region

- English source strings, **English is the default**, German the first translation
  (gettext; compiled `.mo` files are committed so nobody needs gettext just to run or
  build).
- **The region is the main setting** (country for streaming providers, release dates and
  date formats). New users get it from the browser on their first request after login
  (`de-AT` → AT, plain `de` → DE), else `DEFAULT_REGION`, else US. Country names and
  official languages come from Babel (Unicode CLDR).
- **Languages follow the region** unless overridden under "Advanced" in the profile:
  interface = the country's main language if translated, else English; TMDB language =
  main language + country (AT → `de-AT`). Visitors who aren't logged in get their browser
  language if translated, else `DEFAULT_LANGUAGE`.
- **Date and number formats** follow the region: the active language includes the country
  (`en-gb`, `de-at`); texts come from the language's translation, formats from Django's
  format for the country, falling back to the language's.

### Look and feel

- Pages: dashboard, lists, upcoming, search, detail pages, profile, About, Django admin.
  Navigation as a top bar on desktop and a bottom tab bar on phones. The current page is
  colored on a tinted pill (on phones behind the icon, like Android's navigation bar), the
  other entries are gray. Rejected: bold text alone (barely visible at the tab bar's
  small font size).
- Pico CSS (classless, no build step), color scheme follows the system and can be set in
  the profile. Installable as a PWA (manifest, icons, standalone mode; browsers install
  it only over HTTPS).
- **Update only what changes:** htmx responses replace the smallest element (a button,
  one card's text) or remove one entry; re-rendering a whole list rebuilds every poster
  and makes them flicker. Where a region is refreshed but most entries stay (live search,
  list filters, "Undo"), Idiomorph merges old and new HTML instead of replacing it.
- **The back button shows the current state.** Browsers restore the previous page from
  their caches without asking the server: the bfcache keeps the whole page in memory, the
  HTTP cache keeps its HTML. After following a show and going back, the list would still
  lack the bell, which breaks the app feeling, especially in the PWA. Every successful
  change (POST) sets the cookie `couchowl_version` to a new timestamp
  (`core/middleware.py`); pages carry the version they were made with
  (`<main data-version>`). When a page comes back (`pageshow` from the bfcache, a
  back/forward load, an htmx history restore), `couchowl.js` compares both and, only if
  they differ, loads the page again and morphs `<main>` into place (no flicker, scroll
  position stays); a changed interface language or theme reloads the whole page. Because
  Django answers with `Vary: Cookie`, the new cookie also makes Chromium skip its outdated
  HTTP cache copy. Limit: changes made on another device are not noticed (that would need
  a version in the database and a request on every back navigation). Rejected:
  `Cache-Control: no-store` (turns off the bfcache, every back navigation becomes a full
  page load) and always reloading on `pageshow` (same, plus a second load).
- **Toasts** ("S2 E5 watched · Undo") at the bottom disappear after 6 seconds. Without
  JavaScript, actions fall back to full page loads with a message.
- Episode codes are always "S1 E3", not "S01E03".
- Empty states explain how to fill the section.
- The footer shows only the version and links (About, legal notice, privacy). The TMDB
  logo and notice and the JustWatch credit are on the About page, because TMDB's terms ask
  for them in an "About" or "Credits" section.

## TMDB integration

- **Read access token** (`TMDB_API_TOKEN`) sent as a `Bearer` header, never as `?api_key=`
  in URLs, so it doesn't end up in logs.
- **HTTP client:** httpx; tests replace the network with a mock transport.
- **Throttling:** at most 20 requests per second and process; on "429 Too Many Requests"
  the client waits (at most 10 s) and retries up to twice.
- **One request per title:** details come with translations, seasons
  (`append_to_response=season/1,…`, at most 20 per request), streaming providers and
  ratings.
- **Language fallback for titles and descriptions** (from the translations list): exact
  language (`de-AT`) → the language's main country (`de-DE`) → same language, other
  country → English → original title / empty description. TMDB returns no German
  description for many shows with `de-AT`, but does with `de-DE`. **Posters belong to the
  translation** (TMDB has localized posters).
- **Episodes** have no translations list, and `de-AT` returns placeholders ("Episode 1").
  Order: exact language → plain language (`de`) → `en-US`; further languages are only
  requested for seasons still missing descriptions. Name and description always come from
  the same language. Untranslated season names arrive as the English placeholder
  "Season 3"; they are stored empty and shown as the translated default name.
- **Seasons and episodes are identified by their numbers.** Those TMDB no longer lists
  are deleted, together with their watched marks.
- **Three ways data is refreshed:**
  1. **On demand:** opening a detail page or adding a title loads it if missing or older
     than 24 hours.
  2. **Daily:** `manage.py sync_tmdb` at 03:30 UTC reloads every show someone follows or
     is watching, in all their users' TMDB languages; shows loaded in the last 6 hours
     are skipped (`--force` reloads all). One failing show doesn't stop the run. Movies
     aren't synced (only with movie announcements, see backlog).
  3. **Manually:** "Refresh now" on detail pages, "Refresh all" on "Upcoming",
     `sync_tmdb` on the command line.
- **Lists, dashboard and "Upcoming" never ask TMDB**; loading many titles at once would be
  too slow. They show the stored texts, in the nearest stored language if needed.
- **When TMDB is unreachable**, stale data from the database is shown instead of an error.
  Without a token, search shows a notice.
- **Poster proxy** (`/posters/<size>/<file>`): only sizes `w92`, `w185`, `w342`, `w500`
  and valid TMDB file names, only for logged-in users. Files are stored in
  `DATA_DIR/posters` once and never change (a new image has a new name), so browsers may
  cache them for a year. Provider logos use the same proxy.
- Titles are read-only in the Django admin (the data belongs to TMDB).
- JustWatch was rejected as a data source: no official API, and its terms forbid
  unofficial use. Its provider data reaches us through TMDB, with attribution.

## Architecture

- **Django 6.1 + htmx** on Python 3.15 (the newest version Django and all dependencies
  support), managed with uv. Endpoints return HTML fragments via template partials;
  Alpine.js where the browser needs a little logic; own JavaScript stays in one small file
  (`core/static/core/couchowl.js`).
- **No CDN:** htmx, Idiomorph, Alpine.js and Pico are vendored in `core/static/vendor/`
  and served with whitenoise.
- **Apps:** `core` (layout, dashboard, upcoming, About, health, backups), `accounts`
  (users, invitations, profile, rate limits), `catalog` (TMDB, titles, lists, shows,
  posters, sync), `imports` (batch import).
- **Configuration only via environment variables** (django-environ); every variable is
  documented in `.env.example`. Secrets never go into the repository.
- **SQLite by default**; PostgreSQL optional via `DATABASE_URL`.
- **The name appears in one place:** `APP_NAME` in `config/settings.py`. Internal names are
  neutral (`APP_VERSION`, CSS variables `--app-…`), so a rename touches nothing technical.
  Translated sentences contain the name directly, because German needs it in compounds
  ("Couch-Owl-Passwort"). Spelling: "Couch Owl" in texts, `couchowl` for everything
  technical.

### Data model

- `accounts.User` (custom user model from day one): `region`, `ui_language` and
  `tmdb_language` (empty = derived from the region), `theme`, `list_layout`,
  `show_followed_list`.
- `Invitation`: token, optional e-mail, note, `created_by`, `expires_at`, `used_by`.
- `Title` (`tmdb_id` + `media_type`) with language-neutral data (dates, status, networks,
  streaming providers, rating); `TitleTranslation` per language (name, description,
  poster). `Season` and `Episode` (numbers, air dates, runtime) with translation tables.
- `UserList` and `ListItem`.
- `UserSeries`: user, show, `following`, `followed_at`, `status` ("watching" is set on the
  first mark).
- `WatchedMovie` and `WatchedEpisode`: user, title/episode, `watched_at` (nullable =
  unknown date), unique per user.
- `Import` (one per user: state, target list name, defaults) and `ImportLine` (pasted
  text, query, search status, up to 5 candidates as JSON, choice, watched, follow,
  result, `claimed_at`). Candidates are stored, not searched again, so the preview stays as it
  was even after TMDB's search cache expires.
- Announcements, "Continue watching" and the followed-shows list are computed by queries,
  not stored.

## Operations

- **One container** (Compose service `couchowl`): `tini` as PID 1 (forwards signals, reaps
  processes) → entrypoint runs `migrate` → `honcho` starts `web` (gunicorn, `WEB_WORKERS`)
  and `cron` (supercronic: TMDB sync, backup). If one process dies, the container exits
  and Docker restarts it (`restart: unless-stopped`). Logs of both go to `docker logs`.
- **Image:** `python:3.15-slim`, multi-stage; uv installs dependencies into a venv in the
  builder; the final stage has no uv or compiler and runs as uid 1000. Static files are
  collected at build time, so the image stays immutable and the app needs no write access
  to `/app`. Alpine Linux was rejected (musl, wheel problems), distroless too (no shell,
  Python version tied to Debian). amd64 and arm64.
- **`SITE_URL` is the one address setting:** it determines the allowed host, the trusted
  origin for forms, secure cookies and HSTS for https, and the links in e-mails. Separate
  `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are a classic trap (forget the second and
  every form fails behind HTTPS); both remain as optional extras. Links use `SITE_URL`
  because not every proxy forwards the public host name. An https `SITE_URL` without a
  proxy stops the start with a clear message.
- **`TRUSTED_PROXY_COUNT`** (like Express's `trust proxy`, default 0): only then are
  `X-Forwarded-For` and `X-Forwarded-Proto` believed. The client address is the entry the
  outermost trusted proxy appended; entries further left can be forged and are ignored.
  Addresses are normalized (IPv6, ports, IPv4-mapped IPv6). django-axes and all rate
  limits use the same function (`accounts.throttle.client_ip`); gunicorn doesn't trust the
  headers itself. Proxy setups are documented vendor-neutrally.
- **HSTS** with https: one year, no subdomains (other subdomains may be other services),
  no preload (hard to undo); `HSTS_SECONDS=0` turns it off. **No http → https redirect**
  in Couch Owl: the proxy does that, and the container's health check uses http.
- **IPv6 without a proxy:** Docker often forwards IPv6 through its own helper process, so
  Couch Owl only sees Docker's internal address. The docs recommend a reverse proxy.
- **Backups: the app only makes a consistent copy;** keeping it safe (other disk, cloud,
  versions) is the host's job. Copying a live SQLite file can produce a broken copy; only
  the app can copy safely via SQLite's backup API. `manage.py backup` runs at 03:00 UTC
  into `BACKUP_DIR` and keeps `BACKUP_KEEP` copies (default 3; the host keeps versions);
  only files named `couchowl-YYYYMMDD-HHMMSS.sqlite3` are rotated. **No `restore`
  command:** restoring means stopping the container and copying the file back; `migrate`
  brings older copies up to date. PostgreSQL users use `pg_dump`.
- **Versions:** Semantic Versioning, `CHANGELOG.md` in "Keep a Changelog" format, version
  in the footer, on the About page and in the health check. `pyproject.toml` is the single
  source of the version. An update is a new image plus a restart; migrations run on start.
  1.0 starts as a release candidate that is tested in a real installation first.
- **Published image:** `ghcr.io/okoetter/couchowl` (GitHub Container Registry), for
  `linux/amd64` and `linux/arm64` under one tag (multi-arch). GHCR needs no extra account
  or secret (the workflow's own token pushes) and has no pull limits for public images.
  Docker Hub as a second registry was rejected for now: another account and token for
  little gain.
- **Tags:** the Git tag `v1.2.3` produces the image tags `1.2.3`, `1.2`, `1` and `latest`,
  so users can pin as tightly as they like (`COUCHOWL_VERSION` in `.env`, default
  `latest`). Pre-releases (`v1.0.0-rc.1`) get only their own tag and a GitHub
  "Pre-release", so nobody runs a release candidate by accident. Every release, pre-release
  or not, also moves `next`: whoever tests release candidates sets `COUCHOWL_VERSION=next`
  once instead of entering each version. `next` follows the order of publication; ordering
  by version number (no `next` move for a bug fix of an older line) was left out because
  releases are linear so far. No image per push to main (`edge`): every published image
  went through a release.
- **Installation without git:** `docker-compose.yml` pulls the image; the release attaches
  it and `env.example` (GitHub removes leading dots from file names), so
  `releases/latest/download/…` always fetches matching files. Building from source is an
  extra Compose file (`docker-compose.build.yml`): one file with both `image` and `build`
  would sometimes pull and sometimes build, depending on what is cached.
- **Release workflow:** a tag starts `release.yml`. `scripts/release_check.py` first checks
  that tag, `pyproject.toml` and the `CHANGELOG.md` section agree (and turns that section
  into the release notes); then the whole CI runs, with the Docker smoke test on amd64 and
  arm64; only then is the image pushed. arm64 is built with QEMU emulation on the normal
  runners: all dependencies are pure Python, so emulation costs minutes, not hours;
  native arm64 runners would need an extra merge step for the multi-arch tag. Each release
  uses its own Docker build cache, so nothing cached by other branches ends up in an image.
- **Workflow hygiene:** actions are pinned to commit hashes (a tag like `v4` can be moved
  to other code; a hash can't), Dependabot proposes updates with a week's delay, jobs get
  only the permissions they need (only publishing may write packages and releases), and
  actionlint and zizmor check every workflow change.

## Security

- Django defaults (CSRF, secure cookies and HSTS with https), django-axes, rate limits,
  invitation tokens with expiry, poster proxy only for logged-in users.
- A Content Security Policy is in the backlog: the standard build of Alpine.js needs
  `unsafe-eval`; a strict policy needs Alpine's CSP build.

## Open source

- **License: AGPL-3.0-or-later.** Copyleft that also covers network use: whoever runs a
  modified version for others must offer its source code, which is common for self-hosted
  apps. "Or later" (the FSF's recommendation) allows moving to future versions without
  asking every contributor. Contributions are under the same license.
- **About page** (`/about/`, public): version, license, source code link, TMDB logo and
  notice, JustWatch credit, legal links. Public so that the source code and the legal
  links reach every visitor. `SOURCE_URL` can point to a modified version's code.
- **`IMPRINT_URL` and `PRIVACY_URL`** link to pages the operator publishes elsewhere;
  Couch Owl hosts no legal texts. `docs/deployment.md` lists what Couch Owl stores, as a
  basis for a privacy policy.
- **Name:** "Couch Owl" was chosen because nobody in the same field (watchlists,
  trackers, media servers) uses it; checked on GitHub, the web, app stores and in
  trademark notices. Rejected because taken or too close in the same field: Couchplan,
  Sofa…, Snug, CouchSloth, Serialist, Laterna, Couchbuddy, Couchradar (too close to Radarr
  and CouchPotato). The app icon is an owl on a couch.

## Testing

- **pytest-django**, focused on logic and on request → view → database → template
  (including access rules: nobody sees other people's lists, and htmx fragments).
- **TMDB is never called in tests:** the autouse fixture `fake_tmdb` blocks the network
  and serves saved, shortened real responses from `catalog/tests/fixtures/`.
- Tests run in German so the translations are exercised too.
- **Levels:** unit and integration tests (pre-commit hook, with ruff); end-to-end tests
  with Playwright for core flows and screenshots of important pages in light/dark and
  desktop/phone (marker `e2e`, too slow for pre-commit); live checks against the real TMDB
  API (marker `live`, run by hand); a Docker smoke test (`scripts/smoke_test.py`) that
  starts the real image and checks health, version, static files, the non-root user, the
  crontab and a backup.
- **Cross-platform development:** no bash-only scripts, everything runs via `uv run`;
  `.python-version`, `.gitattributes` and `.editorconfig`. CI runs the tests on Linux,
  macOS and Windows; the browser tests only on Linux (they test the browser, not the OS),
  with the screenshots as a downloadable artifact. The smoke test is a Python script, not
  a shell script, so it runs on every OS.
