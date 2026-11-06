# Administration

This guide is for the person running a watchit instance. Commands are shown for Docker Compose;
for local development, replace `docker compose exec watchit` with `uv run`.

## Create the first admin

watchit has no open registration. Create the first account on the command line:

```sh
docker compose exec watchit python manage.py createsuperuser
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

## Locked logins (brute-force protection)

After `AXES_FAILURE_LIMIT` failed logins (default 5), the combination of username and IP address
is locked for `AXES_COOLOFF_MINUTES` (default 60). Other users are not affected.

- See failed attempts and lockouts: **Admin → Axes → Access attempts**
- Unlock everyone: `docker compose exec watchit python manage.py axes_reset`
- Unlock one user: `docker compose exec watchit python manage.py axes_reset_username <username>`

## Set up e-mail

E-mail is optional. Configure it in `.env` (not in the admin) and restart the container:

```ini
EMAIL_URL=smtp+tls://user:password@mail.example.com:587
DEFAULT_FROM_EMAIL=watchit <watchit@example.com>
```

Use `smtp+ssl://…:465` for implicit TLS. Special characters in the user name or password must be
URL-encoded (e.g. `@` → `%40`). Send a test mail:

```sh
docker compose exec watchit python manage.py sendtestemail you@example.com
```
