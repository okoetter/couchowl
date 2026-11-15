from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Import(models.Model):
    """A batch import of one user, kept in the database so the page can be left and resumed.

    Goes through the states in order: the pasted lines are searched on TMDB (analyzing),
    the user checks the matches (preview), the titles are imported (importing), and the
    result is shown (done) until the user starts a new import. One import per user.
    """

    class State(models.TextChoices):
        ANALYZING = "analyzing", _("Analyzing")
        PREVIEW = "preview", _("Preview")
        IMPORTING = "importing", _("Importing")
        DONE = "done", _("Done")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="batch_import",
    )
    state = models.CharField(
        _("state"), max_length=10, choices=State.choices, default=State.ANALYZING
    )
    # Target list by name, empty = no list. A new list is created when importing starts;
    # by name, so a list deleted in the meantime simply comes back.
    list_name = models.CharField(_("list"), max_length=100, blank=True)
    # Defaults for the lines' "watched" and "follow" switches
    watched = models.BooleanField(_("mark as watched"), default=False)
    follow = models.BooleanField(_("follow shows"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("import")
        verbose_name_plural = _("imports")

    def __str__(self):
        return f"{self.user} ({self.get_state_display()})"


class ImportLine(models.Model):
    """One pasted line: what TMDB found for it, the user's choice and the result."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Not searched yet")
        MATCHED = "matched", _("Found")
        AMBIGUOUS = "ambiguous", _("Ambiguous")
        NOT_FOUND = "not_found", _("Not found")

    class Result(models.TextChoices):
        IMPORTED = "imported", _("Imported")
        # Skipped, with the reason (shown on the result page)
        EXISTING = "existing", _("Already there")
        DUPLICATE = "duplicate", _("Same title as an earlier line")
        SKIPPED = "skipped", _("Skipped by you")
        # Not found, or ambiguous without a choice
        MISSING = "missing", _("Not imported")

    # The choice value for "skip this line"
    SKIP = "skip"

    # "import" is a Python keyword, so the field is called "batch"
    batch = models.ForeignKey(
        Import, verbose_name=_("import"), on_delete=models.CASCADE, related_name="lines"
    )
    position = models.PositiveIntegerField(_("position"))
    # The line as pasted (without bullet), for the list of lines that weren't imported
    text = models.CharField(_("line"), max_length=200)
    # What was searched for: the line, or what the user typed in "Search again"
    query = models.CharField(_("search"), max_length=200)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    # The top search results (catalog.services.SearchResult as dicts), best first
    candidates = models.JSONField(_("candidates"), default=list, blank=True)
    # Key of the chosen candidate ("tv-70523"), SKIP, or empty = nothing chosen
    choice = models.CharField(_("choice"), max_length=20, blank=True)
    watched = models.BooleanField(_("mark as watched"), default=False)
    # Shows only: follow the show (ignored for movies)
    follow = models.BooleanField(_("follow"), default=False)
    # Empty until the line has been imported
    result = models.CharField(_("result"), max_length=10, choices=Result.choices, blank=True)
    # Set while a request processes the line, so a second tab leaves it alone
    claimed_at = models.DateTimeField(_("claimed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("import line")
        verbose_name_plural = _("import lines")
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "position"], name="unique_import_position")
        ]

    def __str__(self):
        return self.text

    @property
    def number(self) -> int:
        """Line number as the user sees it (from 1)."""
        return self.position + 1


def candidate_key(candidate: dict) -> str:
    """Same as catalog.services.SearchResult.key, e.g. "tv-70523"."""
    return f"{candidate['media_type']}-{candidate['tmdb_id']}"
