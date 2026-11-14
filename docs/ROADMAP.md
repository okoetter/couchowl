# Roadmap

The reasons behind finished work are in [design.md](design.md).

## Milestones to 1.0

- [x] **0 – Project skeleton:** Django, i18n, base layout with navigation, PWA, Docker, tests, pre-commit
- [x] **1 – Accounts:** invitations, login/logout, profile, password reset, admin docs, brute-force protection
- [x] **2 – TMDB:** API client with caching and language fallback, live search, poster proxy
- [x] **3 – Lists and movies:** private lists (movies and shows mixed), grid/compact view, movie "watched" with date
- [x] **4 – Shows and episodes:** season/episode tracking with dates, "Follow" button, system list "Followed shows" (toggle in profile); shows in lists: progress, "next episode watched" button with undo, watched filter
- [x] **5 – Dashboard:** currently watching with next episode, announcements (next 3 months, configurable via `ANNOUNCEMENT_MONTHS`)
- [x] **6 – Sync and "Upcoming":** daily/manual TMDB sync, streaming providers, upcoming page
- [x] Show page: "Mark earlier episodes too?" after marking an episode or season with gaps
  before it
- [x] TMDB ratings on detail pages, in lists and in search
- [x] **7a – Operations:** security settings behind a reverse proxy (with, without or several
  proxies; IPv4 and IPv6), real client IP for brute-force protection and rate limits, nightly
  consistent database copy (`manage.py backup`, rotation) for the host's backup to pick up
- [x] **Name:** "watchit" was a placeholder; the project is now called **Couch Owl**
  (technical name `couchowl`). The owl app icon follows in 7b
- [x] **7b – Open source:** owl app icon, "About" page (version, license, source code link, TMDB logo and
  notice, JustWatch credit; the footer shrinks to a link), `IMPRINT_URL`/`PRIVACY_URL`,
  AGPL-3.0 license, README, `docs/deployment.md`
- [ ] **7c – CI and release:** switch the deployment guide to the published image, GitHub Actions (tests on Ubuntu/macOS/Windows, E2E, Docker smoke
  test), multi-arch images on GHCR with version tags, `1.0.0-rc.1`; `1.0.0` after a successful
  deployment on the NAS

## Backlog (after 1.0)

- [ ] **JustWatch import (CLI only):** `manage.py import_justwatch <file> --user <name> [--dry-run]`
  - watchlists, watched movies/episodes, followed shows
  - match via IMDb ID (TMDB `/find`), else title + year; report unmatched entries
  - open question: how to obtain the export (no official export; GDPR data request?)
- [ ] **Watch history page:** everything I have watched, independent of lists and follows
  (watched movies and episodes stay stored when a title leaves a list or a show is
  unfollowed, but today they are only visible per title)
  - newest first, grouped by month; episodes of the same show and day collapsed
    ("Dark · S2 E1–E4"); entries with an unknown date in their own group at the end
  - filter movies / shows; links to the detail pages
- [ ] Data export (JSON) and self-service account deletion; later imports (Trakt, TV Time, Letterboxd)
- [ ] Search: toggle "relevance / newest first"
- [ ] Lists: sort (date added, title, year, TMDB rating); "already on list X" in search; note per list entry
- [ ] Lists: multi-select with bulk actions (select all/none, mark as watched, remove)
- [ ] Reorder lists by drag and drop (sorted alphabetically for now)
- [ ] Accessibility review (labels, keyboard, contrast, screen readers with HTMX updates)
- [ ] Content Security Policy (needs the CSP build of Alpine.js; the standard build needs
  `unsafe-eval`)
- [ ] **Movie announcements on the dashboard:** unwatched movies on any of my lists whose
  release falls within the announcement window (no separate "Follow" for movies: being on
  a list already means "I want to see this")
  - release dates per region from TMDB `release_dates` (user's `region`), stored in the DB;
    the dashboard still never asks TMDB
  - show the theatrical and, if known, the digital release ("Cinema 12 Feb · digital 28 Mar");
    fall back to the theatrical date (TMDB often adds digital dates late or never)
  - a movie already in cinemas stays announced until its digital release has passed
  - background sync keeps release dates of unreleased movies on lists up to date (dates
    shift often)
  - section subtitle covers both, e.g. "New seasons and movie releases in the next 3 months";
    show release dates on the movie detail page too
- [ ] Notifications (e-mail/push) for new seasons
- [ ] Per-user announcement window in the profile (1/3/6/12 months; empty = `ANNOUNCEMENT_MONTHS`)
- [ ] Public JSON API (e.g. django-ninja)
- [ ] More UI languages
- [ ] Clean up the poster cache (posters no longer used by any stored title)
