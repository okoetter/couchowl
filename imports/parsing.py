"""Reading the pasted text: one title per line, optionally with a year.

Rules (see docs/design.md, "Batch import"):
- Bullets (`-`, `*`, `•`, `1.`, `1)`) and empty lines are ignored.
- `Dark (2017)`: a year in parentheses is always a year.
- `Dark 2017`: a trailing number may be a year or part of the title ("Wonder Woman 1984",
  "Blade Runner 2049", "1917"). It is not a year when it's the whole line or lies in the
  future; otherwise the title without the number is searched with that year first, and
  the whole line when that finds no exact match.
"""

import re
from dataclasses import dataclass

from django.utils import timezone

MAX_LINES = 500
MAX_LINE_LENGTH = 200

# A bullet needs a space after it ("*batteries not included" is a title) or stands alone
_BULLET = re.compile(r"^(?:[-*•]|\d{1,3}[.)])(?:\s+|$)")
_YEAR_IN_PARENTHESES = re.compile(r"^(?P<title>.*?)\s*\((?P<year>\d{4})\)$")
_TRAILING_NUMBER = re.compile(r"^(?P<title>.*\S)\s+(?P<year>\d{4})$")
# Older numbers are never a release year
_FIRST_YEAR = 1870


def split_lines(text: str) -> list[str]:
    """The non-empty lines of `text` without bullets, with whitespace collapsed."""
    lines = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        line = _BULLET.sub("", line, count=1).strip()
        if line:
            lines.append(line[:MAX_LINE_LENGTH])
    return lines


@dataclass(frozen=True)
class Attempt:
    """One search for a line: the query, and the year a result must have (or None)."""

    query: str
    year: int | None = None


def attempts(line: str) -> list[Attempt]:
    """The searches for `line`, in order; the first one with exactly one match wins."""
    if match := _YEAR_IN_PARENTHESES.match(line):
        title = match["title"]
        if title:
            return [Attempt(title, int(match["year"]))]
        return [Attempt(line)]  # "(1984)" alone
    if match := _TRAILING_NUMBER.match(line):
        year = int(match["year"])
        if _FIRST_YEAR <= year <= timezone.localdate().year:
            return [Attempt(match["title"], year), Attempt(line)]
    return [Attempt(line)]
