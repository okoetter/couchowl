# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Invite-only accounts: admins create one-time invitation links in the Django admin
  (optionally sent by e-mail)
- Login and logout; every page requires login
- Profile page: e-mail, region, color scheme; interface language and language for
  movie/show information under "Advanced"
- Region is detected from the browser on first login; both languages follow the region
  unless chosen explicitly. English is the default interface language
- Change password; "forgot password" by e-mail (only when e-mail is configured, rate-limited)
- Admin action to create password reset links (works without e-mail)
- Brute-force protection with django-axes
- `docs/administration.md`
- Live search for movies and TV shows (TMDB), with results in the user's language;
  exact title matches come first (newest first)
- TMDB client with caching in the database, language fallback (e.g. de-AT → de-DE →
  English) and rate limiting
- Poster proxy: posters are downloaded once and served by watchit, so browsers never
  contact TMDB
- TMDB attribution in the footer
- Private lists: create, rename and delete as many as you like; each holds movies and
  shows mixed. A "Watchlist" is created on the first add if you have no list yet
- "Add to list" menu on detail pages and as a "+" button in search results, including
  creating a new list right from the menu
- List view as poster grid or compact list (remembered per user)
- Watched button for movies right on the list page; filters "all / unwatched / watched"
  and "all / movies / TV shows"
- Detail pages for movies and shows (poster, description, status)
- Mark movies as watched with a date (default today; changeable or "unknown");
  search results and lists show watched movies
- Seasons and episodes on show pages, loaded from TMDB with language fallback for
  episode texts (e.g. de-AT → de → English); other seasons load when opened
- Mark single episodes or whole seasons as watched, with a date (changeable or
  "unknown"); progress and next episode on the show page; specials don't count
- "Follow" button for shows and the system list "Followed shows" (can be hidden in
  the profile)
- Shows in lists: progress button ("12/26") that marks the next episode, with "Undo";
  completely watched shows count as watched in filters and search
- Dates are formatted for the user's region (e.g. 01/12/2017 in the UK, 12/01/2017 in
  the US)
- Dashboard: "Continue watching" lists the followed shows you are watching with their
  next episode and progress; a check button marks that episode as watched (with "Undo").
  Marking the first episode of a show follows it; unfollow to remove it from the dashboard
- Dashboard: announcements of new seasons of followed shows within the next
  `ANNOUNCEMENT_MONTHS` months (default 3), with date and network (e.g. Netflix)
- Show page: the "Next" link scrolls to the episode below the sticky navigation and
  briefly highlights it
- Daily TMDB sync (`manage.py sync_tmdb`, run by the container's cron at 03:30 UTC) for all
  shows someone follows or watches: new seasons and episodes, air dates, streaming providers
- Streaming providers ("Available in Germany": subscription, free, rent, buy) on movie and
  show pages, for the user's region (data from JustWatch via TMDB); announcements also name
  the streaming services
- "Upcoming" page: all known season starts of followed shows plus the next episode of
  running seasons, grouped by month; "Refresh all" reloads the followed shows
- "Refresh now" button on detail pages
- Dashboard: caught-up shows stay in "Continue watching" while their season is running,
  showing when the next episode airs ("in 3 days") instead of the check button
- Show page: marking an episode or season with unwatched episodes before it asks whether
  to mark those too (only the same season, or all), with the date "unknown" and "Undo"
- TMDB ratings ("★ 8.4") on detail pages (with the number of votes), in lists and in
  search; overviews only show ratings with at least 10 votes
- `SITE_URL` setting: one address for allowed host, trusted origin, secure cookies, HSTS
  and the links in e-mails
- Reverse proxy support: `TRUSTED_PROXY_COUNT` makes brute-force protection and rate limits
  use the real client address (IPv4 and IPv6) from `X-Forwarded-For`; forged entries are
  ignored
- Nightly consistent database copy (`manage.py backup`, 03:00 UTC) to `BACKUP_DIR`, keeping
  `BACKUP_KEEP` copies (default 3) for the host's backup
- `docs/deployment.md`: running behind a reverse proxy, IPv6, HSTS; restoring a backup in
  `docs/administration.md`

### Changed
- `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are optional extras now (`SITE_URL` covers them)
- gunicorn no longer trusts `X-Forwarded-Proto` from any sender; only Django does, and only
  with `TRUSTED_PROXY_COUNT` set

### Removed
- `DEFAULT_TMDB_LANGUAGE` setting (derived from the region now)

## [0.1.0] - 2026-11-06

### Added
- Project skeleton: Django 6.1 on Python 3.15, managed with uv
- Custom user model with interface language, TMDB language, region and color scheme
- Internationalization with German as the first language; per-user interface language
- Base layout with Pico CSS, htmx and Alpine.js (served locally, no CDN)
- Responsive navigation: top bar on desktop, bottom tab bar on phones
- Installable PWA (web app manifest, icons)
- Health check endpoint `/healthz/`
- Docker image (Debian slim, multi-stage, non-root) with gunicorn and supercronic in one container
- Test suite (pytest-django) and pre-commit hooks (ruff, migration check, tests)
