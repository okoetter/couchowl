import pytest
from django.urls import reverse

from accounts.models import User


@pytest.fixture
def make_user(db):
    def _make(**kwargs):
        return User.objects.create_user(username="oliver", password="pw-for-tests", **kwargs)

    return _make


def test_anonymous_user_gets_server_default_language(client, db):
    content = client.get(reverse("accounts:login")).content.decode()

    assert '<html lang="de"' in content
    assert "Anmelden" in content


def test_profile_language_overrides_default(client, make_user):
    client.force_login(make_user(ui_language="en"))

    content = client.get(reverse("core:dashboard")).content.decode()

    assert '<html lang="en"' in content
    assert "Lists" in content
    assert "Listen" not in content


def test_empty_profile_language_uses_default(client, make_user):
    client.force_login(make_user(ui_language=""))

    content = client.get(reverse("core:dashboard")).content.decode()

    assert '<html lang="de"' in content


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_explicit_theme_is_applied(client, make_user, theme):
    client.force_login(make_user(theme=theme))

    content = client.get(reverse("core:dashboard")).content.decode()

    assert f'data-theme="{theme}"' in content


def test_auto_theme_follows_system(client, make_user):
    client.force_login(make_user(theme="auto"))

    content = client.get(reverse("core:dashboard")).content.decode()

    assert "data-theme=" not in content
