from datetime import date

import pytest

from imports.parsing import MAX_LINE_LENGTH, Attempt, attempts, split_lines


def test_split_lines_ignores_bullets_and_empty_lines():
    text = "- Dark\n\n-\n* Heat\n• Arrival\n1. Up\n12) Her\n   \n  The   Dark Knight  \r\n"

    assert split_lines(text) == ["Dark", "Heat", "Arrival", "Up", "Her", "The Dark Knight"]


@pytest.mark.parametrize(
    "line",
    ["*batteries not included", "2001: A Space Odyssey", "9 to 5", "-1 Below", "21 Jump Street"],
)
def test_split_lines_keeps_titles_that_look_like_bullets(line):
    assert split_lines(line) == [line]


def test_split_lines_cuts_long_lines():
    assert split_lines("x" * 300) == ["x" * MAX_LINE_LENGTH]


def test_year_in_parentheses_is_always_a_year():
    assert attempts("Dark (2017)") == [Attempt("Dark", 2017)]
    assert attempts("Dark(2017)") == [Attempt("Dark", 2017)]
    assert attempts("Avatar 5 (2031)") == [Attempt("Avatar 5", 2031)]


def test_only_a_year_in_parentheses_is_the_title():
    assert attempts("(1984)") == [Attempt("(1984)")]


def test_trailing_year_is_tried_first_then_the_whole_line():
    assert attempts("Dark 2017") == [Attempt("Dark", 2017), Attempt("Dark 2017")]
    assert attempts("Wonder Woman 1984") == [
        Attempt("Wonder Woman", 1984),
        Attempt("Wonder Woman 1984"),
    ]


@pytest.mark.parametrize("line", ["1917", "Blade Runner 2049", "Space 1001", "Dark"])
def test_not_a_year(line):
    assert attempts(line) == [Attempt(line)]


def test_current_year_is_a_year():
    year = date.today().year

    assert attempts(f"Dune {year}")[0] == Attempt("Dune", year)
