# Deployment

Couch Owl runs as a single Docker container. It speaks plain http on port 8000 and keeps all
data in the volume `/data` (database, poster cache, backups). HTTPS comes from a reverse
proxy in front of it. This guide is independent of the host; any machine with Docker works.
For accounts, e-mail and backups see [administration.md](administration.md).

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

## Data and backups

All data lives in the volume mounted at `/data`. Every night the container writes a
consistent copy of the database to `/data/backups`; include it in your host's backup. See
[administration.md](administration.md#backups-and-restore).
