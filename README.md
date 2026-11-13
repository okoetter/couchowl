# watchit

A self-hosted watchlist for movies and TV shows.

> **Status:** early development (0.1.0). Not ready for use yet – see [docs/ROADMAP.md](docs/ROADMAP.md).

## Planned features (1.0)

- Your own private lists ("My watchlist", "Watch with family", …), filled via TMDB search
- Track TV shows episode by episode, or mark whole seasons as watched
- Dashboard with the next episode of every show you are watching
- Follow shows (automatic "Followed shows" list) and see announcements for new seasons,
  including where they stream
- Invite-only accounts; interface in English and German, picked from your country automatically
- Privacy-friendly: no CDNs, your browser never talks to third parties
- Installable on your phone (PWA); runs as a single small Docker container (SQLite by default)

## Quick start (Docker)

```sh
cp .env.example .env    # then edit: SECRET_KEY, SITE_URL, TMDB_API_TOKEN
docker compose up -d --build
```

Create the first admin account, then open <http://localhost:8000>:

```sh
docker compose exec watchit python manage.py createsuperuser
```

All settings are documented in [.env.example](.env.example). Running watchit behind a
reverse proxy with HTTPS is described in [docs/deployment.md](docs/deployment.md); inviting
users, password resets, e-mail setup and backups in
[docs/administration.md](docs/administration.md).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

This product uses the TMDB API but is not endorsed or certified by TMDB.
