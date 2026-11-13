"""Core account flow in a real browser: invitation -> registration -> login."""

import re

import pytest
from playwright.sync_api import expect

from e2e.conftest import LOCALE, PASSWORD, login

pytestmark = pytest.mark.e2e


def test_invitation_registration_and_login(live_server, admin, browser):
    # Admin creates an invitation in the Django admin and copies the link
    admin_page = browser.new_context(locale=LOCALE).new_page()
    login(admin_page, live_server.url, "admin")
    admin_page.goto(f"{live_server.url}/admin/accounts/invitation/add/")
    admin_page.locator("#id_email").fill("ben@example.com")
    admin_page.locator("input[name=_save]").click()
    link = admin_page.locator("#invitation-link").input_value()
    assert re.fullmatch(rf"{live_server.url}/accounts/register/[\w-]+/", link)

    # The invitee registers in a fresh browser session
    page = browser.new_context(locale=LOCALE).new_page()
    page.goto(link)
    expect(page.locator("#id_email")).to_have_value("ben@example.com")
    page.locator("#id_username").fill("ben")
    page.locator("#id_password1").fill(PASSWORD)
    page.locator("#id_password2").fill(PASSWORD)
    page.get_by_role("button", name="Konto anlegen").click()
    expect(page.get_by_text("Willkommen bei Couch Owl, ben!")).to_be_visible()
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

    # Log out via the profile page, then log in again
    page.get_by_role("link", name="Profil").click()
    page.get_by_role("button", name="Abmelden").click()
    expect(page).to_have_url(f"{live_server.url}/accounts/login/")
    login(page, live_server.url, "ben")
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

    # The invitation link cannot be used a second time
    other = browser.new_context(locale=LOCALE).new_page()
    other.goto(link)
    expect(other.get_by_role("heading", name="Ungültige Einladung")).to_be_visible()


def test_wrong_password_shows_error(live_server, member, page):
    login(page, live_server.url, "anna", "wrong", expect_success=False)

    expect(page.get_by_text("Benutzername oder Passwort ist falsch.")).to_be_visible()


def test_profile_action_buttons_have_equal_height(live_server, member, page):
    login(page, live_server.url, "anna")
    page.goto(f"{live_server.url}/accounts/profile/")

    change = page.get_by_role("button", name="Passwort ändern").bounding_box()
    logout = page.get_by_role("button", name="Abmelden").bounding_box()

    assert change["height"] == pytest.approx(logout["height"], abs=1)
    assert change["y"] == pytest.approx(logout["y"], abs=1)


def test_profile_action_buttons_stack_on_phones(live_server, member, browser):
    page = browser.new_context(locale=LOCALE, viewport={"width": 390, "height": 844}).new_page()
    login(page, live_server.url, "anna")
    page.goto(f"{live_server.url}/accounts/profile/")

    change = page.get_by_role("button", name="Passwort ändern").bounding_box()
    logout = page.get_by_role("button", name="Abmelden").bounding_box()

    assert change["width"] == pytest.approx(logout["width"], abs=1)
    assert change["y"] < logout["y"]  # one below the other
