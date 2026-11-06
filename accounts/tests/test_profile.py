import pytest
from django.urls import reverse

from accounts.models import User


def save_profile(client, **data):
    payload = {
        "email": "oliver@example.com",
        "ui_language": "",
        "tmdb_language": "",
        "theme": "auto",
        "region": "",
    }
    payload.update(data)
    return client.post(reverse("accounts:profile"), payload)


def test_profile_page_shows_settings(auth_client):
    content = auth_client.get(reverse("accounts:profile")).content.decode()

    assert "Profil" in content
    assert "Erweitert" in content
    assert "Serverstandard (de-DE)" in content
    assert "Aktuell verwendet: DE" in content


def test_save_profile(auth_client, user):
    response = save_profile(
        auth_client, ui_language="en", tmdb_language="en-GB", theme="dark", region="at"
    )

    assert response["Location"] == reverse("accounts:profile")
    user.refresh_from_db()
    assert user.ui_language == "en"
    assert user.tmdb_language == "en-GB"
    assert user.theme == "dark"
    assert user.region == "AT"  # normalized to upper case


def test_new_language_applies_after_saving(auth_client):
    save_profile(auth_client, ui_language="en")

    content = auth_client.get(reverse("accounts:profile")).content.decode()

    assert '<html lang="en"' in content
    assert "Your profile has been saved." in content


@pytest.mark.parametrize("region", ["D", "DEU", "1A", "XY", "EU"])
def test_invalid_region_is_rejected(auth_client, user, region):
    response = save_profile(auth_client, region=region)

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.region == ""


@pytest.mark.parametrize("region", ["ch", "GB", " us "])
def test_valid_regions_are_accepted(auth_client, user, region):
    save_profile(auth_client, region=region)

    user.refresh_from_db()
    assert user.region == region.strip().upper()


def test_invalid_region_shows_error_and_opens_advanced(auth_client):
    content = save_profile(auth_client, region="XY").content.decode()

    assert "Gib einen gültigen zweistelligen Ländercode" in content
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
