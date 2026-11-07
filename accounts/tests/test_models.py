import pytest

from accounts.models import User
from accounts.regions import (
    country_choices,
    region_from_accept_language,
    tmdb_language_for_region,
    ui_language_for_region,
)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("de-AT,de;q=0.9,en;q=0.8", "AT"),
        ("de", "DE"),  # no country: most likely country of the language
        ("en", "US"),
        ("pt-br", "BR"),
        ("en-GB;q=0.5,fr-FR", "FR"),  # highest quality wins
        ("*", None),
        ("", None),
        ("xx-YY", None),
    ],
)
def test_region_from_accept_language(header, expected):
    assert region_from_accept_language(header) == expected


@pytest.mark.parametrize(
    ("region", "ui", "tmdb"),
    [
        ("DE", "de", "de-DE"),
        ("AT", "de", "de-AT"),
        ("CH", "de", "de-CH"),
        ("US", "en", "en-US"),
        ("FR", "en", "fr-FR"),  # no French translation yet -> English interface
        ("BE", "en", "nl-BE"),  # main language Dutch, not German
    ],
)
def test_languages_follow_region(settings, region, ui, tmdb):
    settings.LANGUAGE_CODE = "en"

    assert ui_language_for_region(region) == ui
    assert tmdb_language_for_region(region) == tmdb


def test_user_languages_are_derived_from_region(settings):
    settings.LANGUAGE_CODE = "en"
    user = User(username="eva", region="AT")

    assert user.effective_region == "AT"
    assert user.effective_ui_language == "de"
    assert user.effective_tmdb_language == "de-AT"


def test_chosen_languages_win_over_region(settings):
    user = User(username="eva", region="AT", ui_language="en", tmdb_language="en-GB")

    assert user.effective_ui_language == "en"
    assert user.effective_tmdb_language == "en-GB"


@pytest.mark.parametrize(("default", "expected"), [("ch", "CH"), ("", "US"), ("XX", "US")])
def test_region_falls_back_to_server_default_then_us(settings, default, expected):
    settings.DEFAULT_REGION = default

    assert User(username="john").effective_region == expected


def test_country_names_are_translated_and_sorted():
    german = dict(country_choices("de"))
    names = [name for _code, name in country_choices("de")]

    assert german["AT"] == "Österreich"
    assert dict(country_choices("en"))["AT"] == "Austria"
    # umlauts sort like the plain letter: Ägypten before Albanien, Österreich before Polen
    assert names.index("Ägypten") < names.index("Albanien")
    assert names.index("Oman") < names.index("Österreich") < names.index("Polen")
