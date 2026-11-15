from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from catalog.models import UserList

from . import parsing

NEW_LIST = "new"


class ImportForm(forms.Form):
    """The paste form: titles, target list and defaults for the preview."""

    lines = forms.CharField(
        label=_("Titles"),
        widget=forms.Textarea(attrs={"rows": 12, "placeholder": "Dark (2017)\nThe Dark Knight"}),
    )
    # x-model: the page shows "Name of the new list" only for "New list" (Alpine.js)
    target = forms.ChoiceField(
        label=_("Add to list"), required=False, widget=forms.Select(attrs={"x-model": "target"})
    )
    new_list = forms.CharField(
        label=_("Name of the new list"),
        max_length=UserList._meta.get_field("name").max_length,
        required=False,
    )
    watched = forms.BooleanField(
        label=_("Mark all as watched"),
        required=False,
        help_text=_(
            "Can be changed per title before importing. The date stays unknown; shows are "
            "marked as completely watched."
        ),
    )
    follow = forms.BooleanField(
        label=_("Follow imported shows"),
        required=False,
        help_text=_(
            "Can be changed per show before importing. Also shows you unfollowed. Followed "
            "shows appear on the dashboard."
        ),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        # Here and not on the field: "%" would translate the text once, at startup
        self.fields["lines"].help_text = _(
            "One movie or TV show per line, optionally with the year: “Dark (2017)”. "
            "At most %(max)s lines. Nothing is imported before you have checked the matches."
        ) % {"max": parsing.MAX_LINES}
        self.user_lists = {str(user_list.pk): user_list for user_list in user.lists.all()}
        self.fields["target"].choices = [
            ("", _("No list")),
            *((pk, user_list.name) for pk, user_list in self.user_lists.items()),
            (NEW_LIST, _("New list …")),
        ]

    def clean_lines(self):
        lines = parsing.split_lines(self.cleaned_data["lines"])
        if not lines:
            raise ValidationError(_("Paste at least one title."))
        if len(lines) > parsing.MAX_LINES:
            raise ValidationError(
                ngettext(
                    "At most %(max)s lines, this is %(count)s line. Import the list in parts.",
                    "At most %(max)s lines, these are %(count)s lines. Import the list in parts.",
                    len(lines),
                )
                % {"max": parsing.MAX_LINES, "count": len(lines)}
            )
        return lines

    def clean_new_list(self):
        return " ".join(self.cleaned_data["new_list"].split())

    def clean(self):
        data = super().clean()
        target = data.get("target")
        if target == NEW_LIST and not data.get("new_list") and "new_list" not in self.errors:
            self.add_error("new_list", _("Enter a name for the new list."))
        if not (target or data.get("watched") or data.get("follow")):
            raise ValidationError(
                _(
                    "Choose a list, mark the titles as watched or follow the shows; otherwise "
                    "the import has nothing to do."
                )
            )
        return data

    @property
    def list_name(self) -> str:
        """Name of the target list ("" = none); a new list is created when importing."""
        target = self.cleaned_data.get("target")
        if target == NEW_LIST:
            return self.cleaned_data["new_list"]
        if target in self.user_lists:
            return self.user_lists[target].name
        return ""
