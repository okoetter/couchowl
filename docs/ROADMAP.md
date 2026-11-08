# Roadmap

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
- [ ] **7 – Production and open source:** security behind proxy, backups, docs, license, CI, 1.0.0
  - "About watchit" page (version, license, TMDB logo and notice, JustWatch credit); the
    footer may then shrink to a link

## Backlog (after 1.0)

- [ ] **JustWatch import (CLI only):** `manage.py import_justwatch <file> --user <name> [--dry-run]`
  - watchlists, watched movies/episodes, followed shows
  - match via IMDb ID (TMDB `/find`), else title + year; report unmatched entries
  - open question: how to obtain the export (no official export; GDPR data request?)
- [ ] Data export (JSON) and self-service account deletion; later imports (Trakt, TV Time, Letterboxd)
- [ ] Lists: sort (date added, title, year); "already on list X" in search; note per list entry
- [ ] Lists: multi-select with bulk actions (select all/none, mark as watched, remove)
- [ ] Reorder lists by drag and drop (sorted alphabetically for now)
- [ ] Accessibility review (labels, keyboard, contrast, screen readers with HTMX updates)
- [ ] Ratings
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
