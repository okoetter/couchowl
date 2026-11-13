"""About page (version, license, source code, data sources) and the footer links."""

import pytest
from django.conf import settings
from django.urls import reverse

ABOUT = reverse("core:about")


@pytest.mark.django_db
def test_about_page_is_public(client):
    response = client.get(ABOUT)

    assert response.status_code == 200


@pytest.mark.django_db
def test_about_page_shows_version_license_and_source_code(client, settings):
    settings.SOURCE_URL = "https://git.example.com/fork/couchowl"

    content = client.get(ABOUT).content.decode()

    assert f"Version {settings.VERSION}" in content
    assert "GNU Affero General Public" in content
    assert 'href="https://www.gnu.org/licenses/agpl-3.0.html"' in content
    assert "Quellcode:" in content
    assert (
        '<a href="https://git.example.com/fork/couchowl" target="_blank" '
        'rel="noopener noreferrer">git.example.com/fork/couchowl</a>'
    ) in content


def test_source_url_defaults_to_the_official_repository():
    assert settings.SOURCE_URL == "https://github.com/okoetter/couchowl"


@pytest.mark.django_db
def test_about_page_credits_tmdb_and_justwatch(client):
    """Required by the TMDB terms of use: logo and notice in an About section, and
    JustWatch as the source of the streaming providers."""
    content = client.get(ABOUT).content.decode()

    assert "catalog/tmdb-logo.svg" in content
    assert "Dieses Produkt nutzt die TMDB-API" in content
    assert 'href="https://www.justwatch.com/"' in content


@pytest.mark.django_db
def test_legal_links_are_hidden_when_not_configured(client):
    content = client.get(ABOUT).content.decode()

    assert "Impressum" not in content
    assert "Datenschutz" not in content


@pytest.mark.django_db
def test_legal_links_appear_on_about_page_and_in_footer(client, settings):
    settings.IMPRINT_URL = "https://example.com/impressum"
    settings.PRIVACY_URL = "https://example.com/datenschutz"

    content = client.get(ABOUT).content.decode()

    # Once in the footer, once in the "Legal" section
    assert content.count('href="https://example.com/impressum"') == 2
    assert content.count('href="https://example.com/datenschutz"') == 2


def test_footer_links_to_about_page_on_every_page(auth_client, settings):
    settings.IMPRINT_URL = "https://example.com/impressum"

    content = auth_client.get(reverse("core:dashboard")).content.decode()

    assert f'<a href="{ABOUT}">Über</a>' in content
    assert '<a href="https://example.com/impressum" rel="noopener noreferrer">Impressum</a>' in (
        content
    )


@pytest.mark.django_db
def test_footer_on_login_page_links_to_about_page(client):
    content = client.get(reverse("accounts:login")).content.decode()

    assert f'href="{ABOUT}"' in content
