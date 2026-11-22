"""Fixtures for browser end-to-end tests (Playwright).

Run with: uv run pytest -m e2e
"""

import os

import pytest

from accounts.models import User

# Playwright's sync API runs an asyncio event loop in the test thread. Django refuses
# database access from such threads unless explicitly allowed (fine in tests).
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

PASSWORD = "Long-enough-Pa55word"  # noqa: S105


@pytest.fixture
def admin(transactional_db):
    return User.objects.create_superuser(username="admin", password=PASSWORD)


@pytest.fixture
def member(transactional_db):
    return User.objects.create_user(username="anna", email="anna@example.com", password=PASSWORD)


def login(page, base_url, username, password=PASSWORD, *, expect_success=True):
    page.goto(f"{base_url}/accounts/login/")
    page.get_by_label("Benutzername").fill(username)
    page.get_by_label("Passwort").fill(password)
    page.get_by_role("button", name="Anmelden").click()
    if expect_success:
        # Wait until the login POST has finished and redirected away from the login page
        page.wait_for_url(lambda url: "/accounts/login/" not in url)
    else:
        page.wait_for_load_state()


def wait_for_htmx(page):
    """Wait until htmx has finished its swap. Right after a swap, new elements with the id
    of an old one still carry the old one's attributes for ~20 ms (htmx "settles" them, for
    CSS transitions): e.g. the bell keeps the grid's class `follow-toggle-corner` when
    switching to the compact list."""
    page.wait_for_function(
        "!document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')"
    )


# The browser reports German, so new users get region DE and a German interface
# (the tests look for German texts). Used by the `page` fixture of pytest-playwright.
LOCALE = "de-DE"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "locale": LOCALE}
