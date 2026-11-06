from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .countries import COUNTRY_CODES
from .models import User

# Languages TMDB has good coverage for. Values are TMDB language codes.
TMDB_LANGUAGES = [
    ("de-DE", "Deutsch (Deutschland)"),
    ("de-AT", "Deutsch (Österreich)"),
    ("de-CH", "Deutsch (Schweiz)"),
    ("en-US", "English (US)"),
    ("en-GB", "English (UK)"),
    ("es-ES", "Español (España)"),
    ("fr-FR", "Français (France)"),
    ("it-IT", "Italiano (Italia)"),
    ("nl-NL", "Nederlands (Nederland)"),
    ("pl-PL", "Polski (Polska)"),
    ("pt-BR", "Português (Brasil)"),
    ("sv-SE", "Svenska (Sverige)"),
    ("tr-TR", "Türkçe (Türkiye)"),
]


def _check_email_unique(email: str, exclude_pk=None) -> str:
    """E-mail is optional, but if given it must not belong to another account
    (password reset mails are sent to every account with that address)."""
    if not email:
        return email
    others = User.objects.filter(email__iexact=email)
    if exclude_pk is not None:
        others = others.exclude(pk=exclude_pk)
    if others.exists():
        raise ValidationError(_("This e-mail address is already used by another account."))
    return email


class LoginForm(AuthenticationForm):
    """Django's login form with a clearer error message for wrong credentials."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("Username or password is incorrect. Note that both are case-sensitive."),
    }


class RegistrationForm(UserCreationForm):
    """Create an account. Username and password are required, e-mail is optional."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")
        help_texts = {
            "email": _("Optional. Needed if you want to reset a forgotten password yourself."),
        }

    def clean_email(self):
        return _check_email_unique(self.cleaned_data.get("email", ""))


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("email", "ui_language", "tmdb_language", "theme", "region")
        help_texts = {
            "email": _("Optional. Needed if you want to reset a forgotten password yourself."),
            "region": _(
                "Two-letter country code (e.g. AT) for streaming providers and release dates. "
                "Leave empty to derive it from the language for movie and show information."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ui_default = dict(settings.LANGUAGES).get(settings.LANGUAGE_CODE, settings.LANGUAGE_CODE)
        self.fields["ui_language"].choices = [
            ("", _("Server default (%(language)s)") % {"language": ui_default}),
            *settings.LANGUAGES,
        ]
        tmdb_choices = list(TMDB_LANGUAGES)
        current = self.instance.tmdb_language
        if current and current not in dict(tmdb_choices):
            tmdb_choices.append((current, current))  # keep values set via the admin
        self.fields["tmdb_language"] = forms.ChoiceField(
            label=self.fields["tmdb_language"].label,
            required=False,
            choices=[
                (
                    "",
                    _("Server default (%(language)s)")
                    % {"language": settings.DEFAULT_TMDB_LANGUAGE},
                ),
                *tmdb_choices,
            ],
        )

    def clean_email(self):
        return _check_email_unique(self.cleaned_data.get("email", ""), exclude_pk=self.instance.pk)

    def clean_region(self):
        region = self.cleaned_data.get("region", "").strip().upper()
        if region and region not in COUNTRY_CODES:
            raise ValidationError(_("Enter a valid two-letter country code such as DE or AT."))
        return region
