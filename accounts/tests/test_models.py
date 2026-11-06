import pytest

from accounts.models import User, region_from_language


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("de-DE", "DE"),
        ("de-AT", "AT"),
        ("en-us", "US"),
        ("pt_BR", "BR"),
        ("en", "US"),  # no country part -> fallback
        ("", "US"),
    ],
)
def test_region_from_language(language, expected):
    assert region_from_language(language) == expected


def test_effective_values_fall_back_to_server_defaults(settings):
    settings.LANGUAGE_CODE = "de"
    settings.DEFAULT_TMDB_LANGUAGE = "de-DE"
    settings.DEFAULT_REGION = ""
    user = User(username="anna")

    assert user.effective_ui_language == "de"
    assert user.effective_tmdb_language == "de-DE"
    assert user.effective_region == "DE"


def test_region_is_derived_from_users_tmdb_language(settings):
    settings.DEFAULT_REGION = ""
    user = User(username="john", tmdb_language="en-GB")

    assert user.effective_region == "GB"


def test_server_default_region_beats_derived_region(settings):
    settings.DEFAULT_REGION = "ch"
    user = User(username="john", tmdb_language="de-DE")

    assert user.effective_region == "CH"


def test_explicit_user_region_wins(settings):
    settings.DEFAULT_REGION = "CH"
    user = User(username="eva", tmdb_language="de-DE", region="at")

    assert user.effective_region == "AT"
