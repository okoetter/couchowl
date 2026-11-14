# CLAUDE.md – Couch Owl

Self-hosted watchlist for movies and TV shows (TMDB). Django + HTMX, SQLite, one Docker container.
Design decisions and their reasons: `docs/design.md`. Milestones and backlog: `docs/ROADMAP.md`.

## Hard rules
- **Never `git push`, never add remotes, never create GitHub repos.** The maintainer pushes.
- Commit only after the maintainer has tested and said OK. Commits go directly to local `main`.
- Code, comments, commit messages, README/CONTRIBUTING/docs: **English**.
- Work milestone by milestone (see ROADMAP.md). Per milestone: explain → implement + tests →
  run tests → give concrete browser test steps → maintainer reviews diff → commit after OK.
- When decisions change, update the matching section of `docs/design.md` in the same change
  (current state with the reason; note rejected alternatives). New ideas go to the ROADMAP backlog.
  When setup changes, update README/CONTRIBUTING in the same commit.

## Stack and conventions
- Python 3.15, Django 6.1, `uv` for everything (`uv run …`), no bash-only dev scripts.
- No hardcoded UI text: `gettext`/`{% translate %}` everywhere, English source strings,
  German in `locale/de/LC_MESSAGES/django.po`. After changing texts:
  `uv run python manage.py makemessages -l de --ignore=.venv --ignore=staticfiles`, translate,
  `uv run python manage.py compilemessages --ignore=.venv` (commit both .po and .mo).
- Config only via environment variables (`config/settings.py`, documented in `.env.example`).
- Email: Django 6.1 `MAILERS` setting, built from `EMAIL_URL` (`config/mail.py`).
- HTMX endpoints return HTML fragments (Django template partials). CSRF header is set on `<body>`.
  Replace only what changes (rebuilt `<img>` elements flicker): target the smallest element,
  use `hx-swap-oob` for extra spots, and `hx-swap="morph:innerHTML"` (Idiomorph) when a
  region is refreshed but most entries stay; morphed entries need a stable `id`.
- No external resources at runtime (no CDN): vendored libs in `core/static/vendor/`.
  Own JavaScript stays small and lives in `core/static/core/couchowl.js`.
  The browser must never talk to TMDB directly (texts cached in DB, posters via proxy).
- Custom user model `accounts.User` (`ui_language`, `tmdb_language`, `region`, `theme`).
- Tests: pytest-django, settings `config/settings_test.py`. TMDB is always mocked via the autouse
  fixture `fake_tmdb` (`conftest.py`, saved responses in `catalog/tests/fixtures/`)
  (marker `live` for real API checks, `e2e` for Playwright; both skipped by default).
- TMDB code lives in the `catalog` app: `tmdb.py` (HTTP client), `services.py` (search, DB cache,
  language fallback, seasons/episodes), `posters.py` (poster proxy), `lists.py` (lists, watched
  movies, system list "Followed shows"), `shows.py` (follow, watched episodes, progress, next episode),
  `dashboard.py` (continue watching, announcements, upcoming; database only, never asks TMDB),
  `providers.py` (streaming providers per region for display, stored in `Title.watch_providers`),
  `sync.py` (bulk reload: `manage.py sync_tmdb`, "Refresh all").
  Fake shows in tests: `fake_tmdb.add_show()` (details and season requests share a path).
  Views/templates use `{% load catalog %}`
  and `{% poster path "w185" %}` for poster URLs, never TMDB URLs.
- UI changes: add the page to `e2e/test_screenshots.py`, run `uv run pytest -m e2e`, and look at
  the images in `screenshots/` (light/dark, desktop/phone) before asking for a test.
- Form fields render via `core/templates/forms/field.html` (label, input, errors, help text).
- Proxy/HTTPS settings are derived in `config/security.py` from `SITE_URL` and
  `TRUSTED_PROXY_COUNT`. Client IP for rate limits and axes: always `accounts.throttle.client_ip`.
  Absolute links (e-mails, admin): `accounts.links.base_url`, never `build_absolute_uri`.
- TMDB logo/notice and the JustWatch credit live on the About page (`core/about.html`, TMDB
  terms); the footer only links to it. Detail pages keep "Source: JustWatch" next to providers.
- `manage.py backup` (`core/backups.py`) only makes a consistent SQLite copy; the host backs it up.

## Commands
- Dev server: `uv run python manage.py runserver` (needs `.env`, copy from `.env.example`, `DEBUG=True`)
- Tests: `uv run pytest` · Lint/format: `uv run ruff check --fix . && uv run ruff format .`
- All pre-commit hooks: `uv run pre-commit run --all-files`
- Docker (production-like): `docker compose up -d --build`, check `http://localhost:8000/healthz/`

## Container layout
`Dockerfile` (multi-stage, python:3.15-slim, non-root uid 1000) → `tini` → `docker/entrypoint.sh`
(runs `migrate`) → `honcho` with `docker/Procfile`: `web` (gunicorn) + `cron` (supercronic,
`docker/crontab`). If one process dies, the container exits and Docker restarts it.
Runtime data lives in `/data` (DB, poster cache, backups).
