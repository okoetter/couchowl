from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from .models import User
from .regions import country_choices, tmdb_language_for_region, ui_language_for_region

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
    """Region first; both languages are 'automatic' (derived from the region) by default."""

    class Meta:
        model = User
        fields = ("email", "region", "theme", "show_followed_list", "ui_language", "tmdb_language")
        help_texts = {
            "email": _("Optional. Needed if you want to reset a forgotten password yourself."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance
        self.fields["region"] = forms.ChoiceField(
            label=_("Region"),
            choices=country_choices(get_language()),
            help_text=_(
                "Country for streaming providers and release dates. "
                "Also determines the languages below, unless you choose them yourself."
            ),
        )
        self.initial["region"] = user.effective_region

        # "Automatic" shows what the region currently results in
        region_ui = ui_language_for_region(user.effective_region)
        self.fields["ui_language"].choices = [
            ("", _("Automatic (%(language)s)") % {"language": dict(settings.LANGUAGES)[region_ui]}),
            *settings.LANGUAGES,
        ]
        tmdb_choices = list(TMDB_LANGUAGES)
        if user.tmdb_language and user.tmdb_language not in dict(tmdb_choices):
            tmdb_choices.append((user.tmdb_language, user.tmdb_language))  # set via the admin
        self.fields["tmdb_language"] = forms.ChoiceField(
            label=self.fields["tmdb_language"].label,
            required=False,
            choices=[
                (
                    "",
                    _("Automatic (%(language)s)")
                    % {"language": tmdb_language_for_region(user.effective_region)},
                ),
                *tmdb_choices,
            ],
        )

    def clean_email(self):
        return _check_email_unique(self.cleaned_data.get("email", ""), exclude_pk=self.instance.pk)
