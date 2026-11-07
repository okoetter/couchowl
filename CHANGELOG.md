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
- Detail pages for movies and shows (poster, description, status)
- Mark movies as watched with a date (default today; changeable or "unknown");
  search results and lists show watched movies

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
