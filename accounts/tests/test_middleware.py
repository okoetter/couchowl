import pytest
from django.urls import reverse

from accounts.models import User


@pytest.fixture
def make_user(db):
    def _make(**kwargs):
        kwargs.setdefault("region", "DE")
        return User.objects.create_user(username="anna", password="pw-for-tests", **kwargs)

    return _make


def test_anonymous_user_gets_server_default_language(client, db):
    content = client.get(reverse("accounts:login")).content.decode()

    assert '<html lang="de"' in content
    assert "Anmelden" in content


def test_anonymous_user_gets_browser_language(client, db):
    response = client.get(reverse("accounts:login"), headers={"accept-language": "en-GB"})

    assert '<html lang="en"' in response.content.decode()


def test_english_is_the_fallback_for_untranslated_browser_languages(client, db, settings):
    settings.LANGUAGE_CODE = "en"

    response = client.get(reverse("accounts:login"), headers={"accept-language": "fr-FR"})

    assert '<html lang="en"' in response.content.decode()


def test_region_is_detected_from_browser_on_first_request(client, make_user):
    user = make_user(region="")
    client.force_login(user)

    content = client.get(
        reverse("core:dashboard"), headers={"accept-language": "en-GB,en;q=0.9"}
    ).content.decode()

    user.refresh_from_db()
    assert user.region == "GB"
    assert '<html lang="en-gb"' in content


def test_region_falls_back_to_server_default(client, make_user, settings):
    settings.DEFAULT_REGION = "AT"
    user = make_user(region="")
    client.force_login(user)

    client.get(reverse("core:dashboard"))

    user.refresh_from_db()
    assert user.region == "AT"


def test_saved_region_is_not_overwritten_by_browser(client, make_user):
    user = make_user(region="AT")
    client.force_login(user)

    client.get(reverse("core:dashboard"), headers={"accept-language": "en-US"})

    user.refresh_from_db()
    assert user.region == "AT"


def test_interface_language_follows_region(client, make_user, settings):
    settings.LANGUAGE_CODE = "en"
    client.force_login(make_user(region="AT"))

    content = client.get(reverse("core:dashboard")).content.decode()

    assert '<html lang="de-at"' in content


def test_profile_language_overrides_default(client, make_user):
    client.force_login(make_user(ui_language="en"))

    content = client.get(reverse("core:dashboard")).content.decode()

    assert '<html lang="en-de"' in content
    assert "Lists" in content
    assert "Listen" not in content


def test_empty_profile_language_uses_region_language(client, make_user):
    client.force_login(make_user(ui_language="", region="DE"))

    content = client.get(reverse("core:dashboard")).content.decode()

    assert '<html lang="de-de"' in content


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_explicit_theme_is_applied(client, make_user, theme):
    client.force_login(make_user(theme=theme))

    content = client.get(reverse("core:dashboard")).content.decode()

    assert f'data-theme="{theme}"' in content


def test_auto_theme_follows_system(client, make_user):
    client.force_login(make_user(theme="auto"))

    content = client.get(reverse("core:dashboard")).content.decode()

    assert "data-theme=" not in content


@pytest.mark.parametrize(
    ("ui_language", "region", "expected"),
    [
        ("en", "GB", "01/12/2017"),  # texts from "en", date format from the UK
        ("en", "US", "12/01/2017"),
        ("de", "AT", "01.12.2017"),
        ("en", "DE", "12/01/2017"),  # no English format for Germany: the language's
    ],
)
def test_date_format_follows_the_region(make_user, ui_language, region, expected):
    from datetime import date

    from django.test import RequestFactory
    from django.utils import formats, translation

    from accounts.middleware import UserLanguageMiddleware

    request = RequestFactory().get("/")
    request.user = make_user(ui_language=ui_language, region=region)

    def view(request):
        return formats.date_format(date(2017, 12, 1), "SHORT_DATE_FORMAT")

    with translation.override(None):
        assert UserLanguageMiddleware(view)(request) == expected


def test_country_names_ignore_the_region_part():
    from accounts.regions import country_choices

    # Babel has no locale "de_US"; the German names must still be used
    assert dict(country_choices("de-us"))["AT"] == "Österreich"
