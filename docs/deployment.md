# Deployment

Couch Owl runs as a single Docker container. The image is published at
`ghcr.io/okoetter/couchowl` for amd64 and arm64. It speaks plain http on port 8000 and keeps
all data in the volume `/data` (database, poster cache, backups). HTTPS comes from a reverse
proxy in front of it. This guide is independent of the host; any machine with Docker works.
For accounts, e-mail and backups see [administration.md](administration.md).

## Requirements

- Docker with the Compose plugin (`docker compose version`), on amd64 or arm64.
  A small NAS or a Raspberry Pi is enough: Couch Owl uses SQLite by default (PostgreSQL is
  optional) and runs two web server processes (`WEB_WORKERS`) plus a scheduler.
- A free account at [TMDB](https://www.themoviedb.org/) for the API token (see below).
- For access from the internet: a domain name and a reverse proxy with HTTPS.

## Installation

1. **Get the files.** Couch Owl needs only two files from the
   [latest release](https://github.com/okoetter/couchowl/releases/latest): the Compose file
   and the example configuration, saved as `.env`:

   ```sh
   mkdir couchowl && cd couchowl
   curl -fLO https://github.com/okoetter/couchowl/releases/latest/download/docker-compose.yml
   curl -fL https://github.com/okoetter/couchowl/releases/latest/download/env.example -o .env
   ```

   (Or download both in the browser from the release page and rename `env.example` to
   `.env`.)

2. **Configure.** Edit `.env`. Every setting is explained in the file. Set at least:

   | Setting | Value |
   |---|---|
   | `SECRET_KEY` | A long random value, e.g. from `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`. Keep it secret; changing it logs everybody out. |
   | `SITE_URL` | The address people will use, see [below](#two-settings-that-matter). |
   | `TRUSTED_PROXY_COUNT` | `1` behind a reverse proxy, `0` without. |
   | `TMDB_API_TOKEN` | Your TMDB token, see [below](#tmdb-api-token). |
   | `TIME_ZONE` | Your time zone, e.g. `Europe/Berlin` (for "today" and air dates). |

   Optional: `DEFAULT_REGION` (country for new users, e.g. `DE`), `EMAIL_URL` for
   invitations and password resets by e-mail, `IMPRINT_URL` and `PRIVACY_URL` (see
   [Legal notice and privacy policy](#legal-notice-and-privacy-policy)).

3. **Start.** Docker downloads the image on the first start:

   ```sh
   docker compose up -d
   ```

   After a minute, `docker compose ps` shows the container as `healthy`, and
   <http://localhost:8000/healthz/> answers with `{"status": "ok", …}`.

4. **Create the first admin** and invite people, see
   [administration.md](administration.md#create-the-first-admin).

### Versions

By default, Couch Owl runs the newest release (`latest`). To control updates, set
`COUCHOWL_VERSION` in `.env`:

| Value | Runs |
|---|---|
| `latest` (default) | the newest release |
| `1` | the newest 1.x release; no major upgrade with possibly breaking changes |
| `1.2` | the newest 1.2.x release (bug fixes only) |
| `1.2.3` | exactly this version |
| `next` | the most recently published release, release candidates included |

Release candidates (e.g. `1.0.0-rc.1`) are only installed when you set them explicitly
(their version, or `next` to test every one). They are marked "Pre-release" on the
[releases page](https://github.com/okoetter/couchowl/releases) and aren't found by the
`releases/latest` links above: download the two files from the release candidate's page
instead. `next` follows the order of publication, not the version number: a bug fix for an
older version published after a release candidate replaces it.

To build the image from the source code instead (e.g. with your own changes), clone the
repository and use `docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build`.

### TMDB API token

Couch Owl loads all movie and show information from TMDB. Without a token, search and
detail pages don't work.

1. Create a free account at [themoviedb.org](https://www.themoviedb.org/signup).
2. Open **Settings → API** and request an API key (type "Developer"; describe it as a
   personal, non-commercial watchlist).
3. Copy the **API Read Access Token** (a long value starting with `eyJ`), not the short
   "API Key", into `TMDB_API_TOKEN`.

## Two settings that matter

| Setting | Meaning |
|---|---|
| `SITE_URL` | The address people type, e.g. `https://couchowl.example.com` (no path). Sets the allowed host name, secure cookies and HSTS for https, and the links in invitation and password reset e-mails. |
| `TRUSTED_PROXY_COUNT` | How many reverse proxies sit in front of Couch Owl (usually `1`). Only then does Couch Owl believe the `X-Forwarded-For` and `X-Forwarded-Proto` headers. |

Set both in `.env` and restart the container (`docker compose up -d`).

## Home network only (no reverse proxy)

```ini
SITE_URL=http://192.168.1.20:8000
TRUSTED_PROXY_COUNT=0
```

Without HTTPS, passwords travel unencrypted. Don't make port 8000 reachable from the
internet this way.

Phones can't install Couch Owl as an app this way either: browsers only install web apps
served over HTTPS. Over plain http they offer just a shortcut on the home screen, which
opens Couch Owl in a normal browser tab with the address bar.

## Behind a reverse proxy (HTTPS)

The reverse proxy accepts HTTPS connections, holds the certificate and forwards requests to
`http://<docker host>:8000`.

```ini
SITE_URL=https://couchowl.example.com
TRUSTED_PROXY_COUNT=1
```

The proxy must:

- **append** the client address to `X-Forwarded-For`
- set `X-Forwarded-Proto` to `https`
- pass on the `Host` header (or at least forward to a host name Couch Owl accepts; links in
  e-mails always use `SITE_URL`)
- redirect http to https (Couch Owl doesn't, so the container's own health check can use http)

Most proxies do the first two by default. Two examples:

```caddyfile
# Caddy: sets all headers itself
couchowl.example.com {
    reverse_proxy localhost:8000
}
```

```nginx
# nginx (inside the server block for couchowl.example.com with ssl)
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

If the proxy runs on the same machine, publish port 8000 only locally, so nobody can bypass
the proxy: in `docker-compose.yml` use `"127.0.0.1:8000:8000"` instead of `"8000:8000"`.

### Why `TRUSTED_PROXY_COUNT` must be right

Behind a proxy, every request seems to come from the proxy. Couch Owl locks a user name after
failed logins per client address (brute-force protection) and limits password reset
requests per address. It needs the real client address for that, which only the proxy knows.
Each proxy appends the address it saw to `X-Forwarded-For`; Couch Owl takes the entry that
your proxies added and ignores everything further left, which the client may have made up.

- **Too low** (e.g. `0` behind a proxy): all users share the proxy's address. A few wrong
  passwords lock out that user name for everyone, everywhere.
- **Too high** (e.g. `1` without a proxy): attackers can send a fake `X-Forwarded-For` with
  every attempt and are never locked out.

Count every proxy that adds to `X-Forwarded-For`, e.g. `2` for a tunnel or CDN in front of
your own reverse proxy.

**Check it:** log in once with a wrong password from outside, then open
**Admin → Axes → Access attempts**. The IP address must be your device's public address,
not the proxy's. Delete the entry afterwards (or log in correctly).

### IPv6

Couch Owl handles IPv4 and IPv6 client addresses alike. Without a reverse proxy, though,
Docker often forwards IPv6 connections through its own helper process, and Couch Owl only
sees Docker's internal address for every visitor (with the lockout problem described above).
A reverse proxy on the host avoids this: it connects to Couch Owl via IPv4 and passes the
real IPv6 address on in `X-Forwarded-For`.

### HSTS

With an https `SITE_URL`, Couch Owl tells browsers to use only https for this host name for
one year (HSTS, only for this exact name, not its subdomains). While you are still setting
things up, or if your proxy already sends this header, set `HSTS_SECONDS=0`.

## Legal notice and privacy policy

Depending on your country, a website that strangers can reach may need a legal notice
(e.g. the German "Impressum") or a privacy policy. Couch Owl doesn't host these pages; it
links to pages you publish elsewhere:

```ini
IMPRINT_URL=https://example.com/legal-notice
PRIVACY_URL=https://example.com/privacy
```

The links appear in the footer of every page and on the About page, also for visitors who
aren't logged in.

For a privacy policy: Couch Owl stores the account data (user name, optional e-mail
address, settings), the lists and what was watched when, in its own database. It sets only
the cookies it needs (login session, form protection, short status messages). Browsers never contact
TMDB or other third parties; Couch Owl itself talks to TMDB (without any user data) and
serves the posters itself.

## Updates

Read the [changelog](../CHANGELOG.md) or the
[release notes](https://github.com/okoetter/couchowl/releases) first, then:

```sh
docker compose pull
docker compose up -d
```

With a fixed `COUCHOWL_VERSION`, change it in `.env` first. If you installed Couch Owl with
`git clone` before images were published, `git pull` once brings the new
`docker-compose.yml`; from then on, the commands above work and your data stays as it is.

Database changes (migrations) run automatically when the container starts. Older backups
can still be restored afterwards: they are brought up to date on the next start.

## Logs

```sh
docker compose logs -f couchowl
```

Lines from the web server start with `web |`, those from the nightly jobs (TMDB sync,
backup) with `cron |`. `LOG_LEVEL=DEBUG` in `.env` shows more.

## Data and backups

All data lives in the volume mounted at `/data`. Every night the container writes a
consistent copy of the database to `/data/backups`; include it in your host's backup. See
[administration.md](administration.md#backups-and-restore).
