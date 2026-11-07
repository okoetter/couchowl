# Roadmap

## Milestones to 1.0

- [x] **0 – Project skeleton:** Django, i18n, base layout with navigation, PWA, Docker, tests, pre-commit
- [x] **1 – Accounts:** invitations, login/logout, profile, password reset, admin docs, brute-force protection
- [x] **2 – TMDB:** API client with caching and language fallback, live search, poster proxy
- [x] **3 – Lists and movies:** private lists (movies and shows mixed), grid/compact view, movie "watched" with date
- [x] **4 – Shows and episodes:** season/episode tracking with dates, "Follow" button, system list "Followed shows" (toggle in profile); shows in lists: progress, "next episode watched" button with undo, watched filter
- [ ] **5 – Dashboard:** currently watching with next episode, announcements (next 3 months, configurable via `ANNOUNCEMENT_MONTHS`)
- [ ] **6 – Sync and "Upcoming":** daily/manual TMDB sync, streaming providers, upcoming page
- [ ] **7 – Production and open source:** security behind proxy, backups, docs, license, CI, 1.0.0

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
- [ ] Notifications (e-mail/push) for new seasons
- [ ] Per-user announcement window in the profile (1/3/6/12 months; empty = `ANNOUNCEMENT_MONTHS`)
- [ ] Public JSON API (e.g. django-ninja)
- [ ] More UI languages
- [ ] Clean up the poster cache (posters no longer used by any stored title)
