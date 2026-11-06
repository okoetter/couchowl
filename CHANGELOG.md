# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Invite-only accounts: admins create one-time invitation links in the Django admin
  (optionally sent by e-mail)
- Login and logout; every page requires login
- Profile page: e-mail, interface language, language for movie/show information,
  color scheme, region (under "Advanced")
- Change password; "forgot password" by e-mail (only when e-mail is configured, rate-limited)
- Admin action to create password reset links (works without e-mail)
- Brute-force protection with django-axes
- `docs/administration.md`

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
