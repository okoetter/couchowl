# Administration

This guide is for the person running a Couch Owl instance. Commands are shown for Docker Compose;
for local development, replace `docker compose exec couchowl` with `uv run`.

## Create the first admin

Couch Owl has no open registration. Create the first account on the command line:

```sh
docker compose exec couchowl python manage.py createsuperuser
```

Then log in at `https://your-host/admin/` (Django admin) or the normal login page.

## Invite people

1. Open **Admin → Invitations → Add invitation**.
2. Optionally enter the person's e-mail address and a note for yourself.
   The link is valid for `INVITATION_EXPIRY_DAYS` days (default 7); you can change the date.
3. Click **Save**. The invitation opens again and shows the **invitation link**.
   - Copy the link and send it any way you like (messenger, e-mail, …).
   - If e-mail is configured (`EMAIL_URL`) and you entered an address, the link is also
     sent by e-mail automatically.
4. The person opens the link, chooses a username and password and is logged in.

Each link works exactly once. The list shows whether an invitation is *open*, *used* or
*expired*. To resend links by e-mail, select invitations in the list and use the action
**Send invitation by e-mail**.

## Reset a password without e-mail

If `EMAIL_URL` is not set, users can't reset their password themselves; the login page tells
them to contact you.

1. Open **Admin → Users**, select the user.
2. Choose the action **Create password reset link** and click **Go**.
3. Send the displayed link to the user. It is valid for `PASSWORD_RESET_TIMEOUT_HOURS`
   (default 24) and becomes invalid once used or when the password changes.

With e-mail configured, users can use **Forgot your password?** on the login page. That page
never reveals whether an address exists and is limited to 5 requests per hour and IP address.

## Deactivate a user

Open the user in the admin and uncheck **Active**. The user can no longer log in; their data
is kept. Deleting the user removes their data.

## How long logins last

Users stay logged in until they haven't visited Couch Owl for `SESSION_DAYS` days
(default 90); every visit starts the period again. To end logins early:

- Logging out ends the login on that device.
- Changing the password ends the user's logins on all other devices, e.g. after losing a
  phone.
- Deactivating a user (see above) ends all their logins.

## Locked logins (brute-force protection)

After `AXES_FAILURE_LIMIT` failed logins (default 5), the combination of username and IP address
is locked for `AXES_COOLOFF_MINUTES` (default 60). Other users are not affected.

- See failed attempts and lockouts: **Admin → Axes → Access attempts**
- Unlock everyone: `docker compose exec couchowl python manage.py axes_reset`
- Unlock one user: `docker compose exec couchowl python manage.py axes_reset_username <username>`

## TMDB sync

Once a day (03:30 UTC) the container runs `manage.py sync_tmdb`. It reloads every show that
someone follows or is watching: new seasons and episodes, air dates and streaming providers.
Shows loaded within the last 6 hours are skipped. The result appears in `docker logs`
(lines starting with `cron |`). Run it by hand:

```sh
docker compose exec couchowl python manage.py sync_tmdb             # summary only
docker compose exec couchowl python manage.py sync_tmdb --force -v 2 # all shows, one line each
```

Users can also reload a single title ("Refresh now" on its page) or all shows they follow
("Refresh all" on the page "Upcoming").

## Backups and restore

Couch Owl stores everything in one SQLite file (`/data/db.sqlite3`). Copying that file while
Couch Owl writes to it can give a broken copy. So every night (03:00 UTC) the container runs
`manage.py backup`, which writes a consistent copy to `BACKUP_DIR` (default `/data/backups`)
and keeps the newest `BACKUP_KEEP` copies (default 3):

```
/data/backups/couchowl-20261113-030000.sqlite3
```

**Couch Owl does not keep your backups safe – that is your host's job.** Include the backup
folder in your regular backup (another disk, another machine, the cloud), with as many
versions as you like. Back up the copies, not the live `db.sqlite3`. To make that easier,
mount a host folder for the copies (see `docker-compose.yml`, then set `BACKUP_DIR`).
The poster cache needs no backup; posters are downloaded again when needed.

Make a copy by hand, e.g. before an update:

```sh
docker compose exec couchowl python manage.py backup
```

### Restore

Stop Couch Owl first, so nothing writes to the database while it is replaced. Then copy a
backup over the database and start Couch Owl again:

```sh
docker compose stop
docker compose run --rm --entrypoint cp couchowl /data/backups/couchowl-20261113-030000.sqlite3 /data/db.sqlite3
docker compose start
```

Everything is back to the state of that backup (accounts, lists, watched episodes). On
start, Couch Owl updates an older backup to the current database schema automatically.
List the available copies with
`docker compose run --rm --entrypoint ls couchowl -l /data/backups`.

### PostgreSQL

With `DATABASE_URL` pointing to PostgreSQL, `manage.py backup` refuses to run. Use
PostgreSQL's own tools instead, e.g.
`docker compose exec db pg_dump -U couchowl couchowl > couchowl.sql`.

## Set up e-mail

E-mail is optional. Configure it in `.env` (not in the admin) and restart the container:

```ini
EMAIL_URL=smtp+tls://user:password@mail.example.com:587
DEFAULT_FROM_EMAIL=Couch Owl <couchowl@example.com>
```

Use `smtp+ssl://…:465` for implicit TLS. Special characters in the user name or password must be
URL-encoded (e.g. `@` → `%40`). Send a test mail:

```sh
docker compose exec couchowl python manage.py sendtestemail you@example.com
```
