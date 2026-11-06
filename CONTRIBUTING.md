# Contributing to watchit

## Development setup

You need **git** and **[uv](https://docs.astral.sh/uv/)**. uv installs the right Python version
(see `.python-version`) automatically. Docker is only needed to test the production image.

| OS | Install |
|---|---|
| Arch / EndeavourOS | `sudo pacman -S git uv` |
| Debian / Ubuntu | `sudo apt install git` and `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| macOS | `brew install git uv` |
| Windows | `winget install Git.Git astral-sh.uv` |

Docker: Docker Engine on Linux, Docker Desktop on macOS/Windows.

```sh
git clone <repository-url> watchit && cd watchit
uv sync                              # creates .venv with all dependencies
cp .env.example .env                 # Windows: copy .env.example .env
```

Edit `.env` for development:

```ini
DEBUG=True
SECRET_KEY=any-local-value
EMAIL_URL=consolemail://
```

Then:

```sh
uv run pre-commit install            # run checks and tests before every commit
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver    # http://localhost:8000
```

## Everyday commands

| Task | Command |
|---|---|
| Run tests | `uv run pytest` |
| Lint and format | `uv run ruff check --fix .` and `uv run ruff format .` |
| All pre-commit checks | `uv run pre-commit run --all-files` |
| New migration after model changes | `uv run python manage.py makemigrations` |
| Production-like test in Docker | `docker compose up -d --build`, then open `http://localhost:8000` |

## Translations

Source strings in code and templates are English. Never hardcode UI text: use
`gettext` / `gettext_lazy` in Python and `{% translate %}` / `{% blocktranslate %}` in templates.

Updating or adding a language requires GNU gettext (`msgfmt`):

```sh
uv run python manage.py makemessages -l de --ignore=.venv --ignore=staticfiles
# translate locale/de/LC_MESSAGES/django.po
uv run python manage.py compilemessages --ignore=.venv
```

Commit both the `.po` and the compiled `.mo` file. To add a language, also add it to
`LANGUAGES` in `config/settings.py`.

## App icon

`core/static/core/icon.svg` and `icon-maskable.svg` are the sources. Regenerate the PNGs with
`rsvg-convert` (librsvg):

```sh
cd core/static/core
rsvg-convert -w 192 -h 192 icon.svg -o icon-192.png
rsvg-convert -w 512 -h 512 icon.svg -o icon-512.png
rsvg-convert -w 180 -h 180 icon-maskable.svg -o apple-touch-icon.png
rsvg-convert -w 512 -h 512 icon-maskable.svg -o icon-maskable-512.png
```

## Conventions

- Code, comments, commit messages and docs in English.
- Configuration only via environment variables; document new ones in `.env.example`.
- Frontend libraries are vendored in `core/static/vendor/` (no CDNs).
- Tests never call the real TMDB API (use fixtures/mocks).
- Keep [CHANGELOG.md](CHANGELOG.md) up to date (Keep a Changelog format).
