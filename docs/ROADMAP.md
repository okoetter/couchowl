# Roadmap

## Milestones to 1.0

- [x] **0 – Project skeleton:** Django, i18n, base layout with navigation, PWA, Docker, tests, pre-commit
- [x] **1 – Accounts:** invitations, login/logout, profile, password reset, admin docs, brute-force protection
- [ ] **2 – TMDB:** API client with caching and language fallback, live search, poster proxy
- [ ] **3 – Lists and movies:** private lists (movies and shows mixed), grid/compact view, movie "watched" with date
- [ ] **4 – Shows and episodes:** season/episode tracking with dates, "Follow" button, system list "Followed shows" (toggle in profile)
- [ ] **5 – Dashboard:** currently watching with next episode, announcements (next 3 months)
- [ ] **6 – Sync and "Upcoming":** daily/manual TMDB sync, streaming providers, upcoming page
- [ ] **7 – Production and open source:** security behind proxy, backups, docs, license, CI, 1.0.0

## Backlog (after 1.0)

- [ ] **JustWatch import (CLI only):** `manage.py import_justwatch <file> --user <name> [--dry-run]`
  - watchlists, watched movies/episodes, followed shows
  - match via IMDb ID (TMDB `/find`), else title + year; report unmatched entries
  - open question: how to obtain the export (no official export; GDPR data request?)
- [ ] Data export (JSON) and self-service account deletion; later imports (Trakt, TV Time, Letterboxd)
- [ ] Lists: sort and filter; "already on list X" in search; note per list entry
- [ ] Accessibility review (labels, keyboard, contrast, screen readers with HTMX updates)
- [ ] Ratings
- [ ] Notifications (e-mail/push) for new seasons
- [ ] Public JSON API (e.g. django-ninja)
- [ ] More UI languages (English first)
