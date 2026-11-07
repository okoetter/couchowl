import pytest
from django.urls import reverse

from accounts.models import User


def save_profile(client, **data):
    payload = {
        "email": "oliver@example.com",
        "ui_language": "",
        "tmdb_language": "",
        "theme": "auto",
        "region": "DE",
    }
    payload.update(data)
    return client.post(reverse("accounts:profile"), payload)


def test_profile_page_shows_settings(auth_client):
    content = auth_client.get(reverse("accounts:profile")).content.decode()

    assert "Profil" in content
    assert "Erweitert" in content
    assert '<option value="DE" selected>Deutschland</option>' in content
    assert "Automatisch (Deutsch)" in content
    assert "Automatisch (de-DE)" in content


def test_save_profile(auth_client, user):
    response = save_profile(
        auth_client, ui_language="en", tmdb_language="en-GB", theme="dark", region="AT"
    )

    assert response["Location"] == reverse("accounts:profile")
    user.refresh_from_db()
    assert user.ui_language == "en"
    assert user.tmdb_language == "en-GB"
    assert user.theme == "dark"
    assert user.region == "AT"


def test_new_language_applies_after_saving(auth_client):
    save_profile(auth_client, ui_language="en")

    content = auth_client.get(reverse("accounts:profile")).content.decode()

    assert '<html lang="en-de"' in content
    assert "Your profile has been saved." in content


@pytest.mark.parametrize("region", ["", "D", "de", "XY", "EU"])
def test_invalid_region_is_rejected(auth_client, user, region):
    response = save_profile(auth_client, region=region)

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.region == "DE"


def test_changing_region_changes_automatic_languages(auth_client, user):
    save_profile(auth_client, region="US")

    user.refresh_from_db()
    assert user.effective_ui_language == "en"
    assert user.effective_tmdb_language == "en-US"
    content = auth_client.get(reverse("accounts:profile")).content.decode()
    assert '<html lang="en-us"' in content
    assert "Automatic (English)" in content
    assert "Automatic (en-US)" in content


def test_invalid_language_opens_advanced_section(auth_client):
    content = save_profile(auth_client, tmdb_language="xx-YY").content.decode()

    assert "<details open>" in content


def test_unknown_tmdb_language_is_rejected(auth_client, user):
    response = save_profile(auth_client, tmdb_language="xx-YY")

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.tmdb_language == ""


def test_email_of_another_account_is_rejected(auth_client, user):
    User.objects.create_user(username="anna", email="anna@example.com")

    response = save_profile(auth_client, email="anna@example.com")

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.email == "oliver@example.com"


def test_email_can_be_removed(auth_client, user):
    save_profile(auth_client, email="")

    user.refresh_from_db()
    assert user.email == ""


def test_followed_shows_list_can_be_switched_off_and_on(auth_client, user):
    content = auth_client.get(reverse("accounts:profile")).content.decode()
    assert 'id="id_show_followed_list" checked' in content

    save_profile(auth_client)  # unchecked checkboxes are not sent
    user.refresh_from_db()
    assert not user.show_followed_list

    save_profile(auth_client, show_followed_list="on")
    user.refresh_from_db()
    assert user.show_followed_list
