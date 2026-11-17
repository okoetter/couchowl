# Contributing to Couch Owl

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
git clone https://github.com/okoetter/couchowl.git && cd couchowl
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
| Production-like test in Docker | `docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build`, then open `http://localhost:8000` |
| Smoke test of the Docker image | `uv run python scripts/smoke_test.py` (builds the image, starts it and checks it) |

## Browser tests (end-to-end)

A few core flows are tested in a real browser with [Playwright](https://playwright.dev/python/).
They are slower and not part of the pre-commit hook. Install the browser once (Chromium,
about 150 MB, goes to your user cache directory):

```sh
uv run playwright install chromium
```

Run them:

```sh
uv run pytest -m e2e                            # all browser tests
uv run pytest -m e2e e2e/test_screenshots.py    # only screenshots
```

`e2e/test_screenshots.py` saves screenshots of important pages (light/dark, desktop/phone)
to `screenshots/` (ignored by git) for a quick visual review. Add `--headed` to watch the browser.

## Checks against the real TMDB API

Tests marked `live` call the real TMDB API to detect changes in its responses. They are
skipped by default and need `TMDB_API_TOKEN` in your `.env`:

```sh
uv run pytest -m live
```

## Continuous integration

GitHub Actions run on every push to `main` and every pull request
(`.github/workflows/ci.yml`):

- **Lint:** the pre-commit checks without the tests
- **Tests** on Linux, macOS and Windows
- **Browser tests** on Linux; the screenshots are attached to the run as an artifact
  ("screenshots", kept 14 days)
- **Docker smoke test:** builds the image and runs `scripts/smoke_test.py` against it

Changes to `.github/` are checked by two extra pre-commit hooks,
[actionlint](https://github.com/rhysd/actionlint) and [zizmor](https://docs.zizmor.sh/)
(security). They are installed on first use (`uv run --group workflows`). Actions are
pinned to commit hashes; Dependabot proposes updates weekly.

## Releases

Versions follow [Semantic Versioning](https://semver.org/). To release, e.g. `1.2.0`:

1. Push everything that goes into the release to `main` and wait until CI is green there.
   Browser tests can fail on the CI runner but not locally (other system fonts, so text
   has other widths); finding that out before the release commit keeps the tag in place.
2. Set `version = "1.2.0"` in `pyproject.toml` and run `uv lock`.
3. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [1.2.0] - YYYY-MM-DD` (today) and add
   a new empty `## [Unreleased]` above it.
4. Commit, then tag and push: `git tag -a v1.2.0 -m "Couch Owl 1.2.0"` and
   `git push origin main v1.2.0`.

The tag starts `.github/workflows/release.yml`. It checks that tag, `pyproject.toml` and
`CHANGELOG.md` agree, runs the whole CI (with the Docker smoke test also on arm64), then
pushes the image `ghcr.io/okoetter/couchowl` for amd64 and arm64 and creates a GitHub
Release with the changelog section, `docker-compose.yml` and `env.example`.

| Git tag | Image tags |
|---|---|
| `v1.2.0` | `1.2.0`, `1.2`, `1`, `latest` |
| `v1.3.0-rc.1` (pre-release) | `1.3.0-rc.1` only; the GitHub Release is marked "Pre-release" |

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
- Tests never call the real TMDB API. The autouse fixture `fake_tmdb` (in `conftest.py`)
  blocks the network; register the responses a test needs, e.g.
  `fake_tmdb.add("/3/search/multi", json=load_tmdb_fixture("search_multi"))`.
  Saved (shortened) real responses live in `catalog/tests/fixtures/`.
- Keep [CHANGELOG.md](CHANGELOG.md) up to date (Keep a Changelog format).
- [docs/design.md](docs/design.md) explains why things are the way they are; update it when
  a decision changes.

## License

Couch Owl is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE).
By contributing, you agree that your contributions are licensed under the same terms.
