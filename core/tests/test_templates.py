"""Checks that apply to all templates of the project."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES = sorted(
    path
    for folder in ("accounts", "catalog", "core", "templates")
    for path in (ROOT / folder).rglob("templates/**/*")
    if path.suffix in (".html", ".txt")
) + sorted((ROOT / "templates").rglob("*.html"))

# "{#" without "#}" on the same line
UNCLOSED_COMMENT = re.compile(r"\{#(?!.*#\})")


def test_templates_are_found():
    assert len(TEMPLATES) > 10


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda path: str(path.relative_to(ROOT)))
def test_no_multiline_short_comments(path):
    """Django's {# … #} only works on one line; longer comments need {% comment %}.

    A {# that spans lines is not a comment: Django shows it as text on the page.
    """
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        assert not UNCLOSED_COMMENT.search(line), (
            f"{path.name}:{number}: use {{% comment %}} for multi-line comments"
        )
