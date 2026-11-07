import pytest
from django.conf import settings
from django.urls import reverse


def test_dashboard_renders_in_german_by_default(auth_client):
    response = auth_client.get(reverse("core:dashboard"))

    assert response.status_code == 200
    content = response.content.decode()
    assert '<html lang="de-de"' in content
    assert "Willkommen bei watchit" in content
    # Navigation is translated and marks the current page
    assert "Demnächst" in content
    assert 'aria-current="page"' in content


def test_assets_are_served_locally_without_cdn(auth_client):
    content = auth_client.get(reverse("core:dashboard")).content.decode()

    assert "/static/vendor/htmx.min.js" in content
    assert "/static/vendor/pico.min.css" in content
    for cdn in ("jsdelivr", "unpkg", "cdnjs", "googleapis"):
        assert cdn not in content


@pytest.mark.parametrize("name", ["upcoming"])
def test_placeholder_pages_exist(auth_client, name):
    response = auth_client.get(reverse(f"core:{name}"))

    assert response.status_code == 200
    assert "Diese Seite kommt bald." in response.content.decode()


@pytest.mark.django_db
def test_health_reports_ok_and_version(client):
    response = client.get(reverse("core:health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": settings.VERSION}


def test_health_rejects_post(client):
    assert client.post(reverse("core:health")).status_code == 405


@pytest.mark.django_db
def test_manifest_is_valid_pwa_manifest(client):
    response = client.get(reverse("core:manifest"))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/manifest+json"
    data = response.json()
    assert data["display"] == "standalone"
    assert data["start_url"] == "/"
    assert data["description"] == "Deine Watchlist für Filme und Serien"
    sizes = {icon["sizes"] for icon in data["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(icon.get("purpose") == "maskable" for icon in data["icons"])
