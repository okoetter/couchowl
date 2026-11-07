from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import UserList


class ListForm(forms.ModelForm):
    """Create or rename a list. Names are unique per user (ignoring case)."""

    class Meta:
        model = UserList
        fields = ("name",)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["name"].widget.attrs["placeholder"] = _("e.g. Watch with family")

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        others = self.user.lists.filter(name__iexact=name)
        if self.instance.pk:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise ValidationError(_("You already have a list with this name."))
        return name

    def save(self, commit=True):
        self.instance.user = self.user
        return super().save(commit)


class WatchedDateForm(forms.Form):
    """Change the date of a watched movie: a day, or "unknown"."""

    watched_at = forms.DateField(
        label=_("Watched on"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    unknown = forms.BooleanField(label=_("Date unknown"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["watched_at"].widget.attrs["max"] = timezone.localdate().isoformat()

    def clean(self):
        data = super().clean()
        if data.get("unknown"):
            data["watched_at"] = None
        elif not data.get("watched_at"):
            if "watched_at" not in self.errors:
                self.add_error("watched_at", _("Enter a date or choose “Date unknown”."))
        elif data["watched_at"] > timezone.localdate():
            self.add_error("watched_at", _("The date can't be in the future."))
        return data
