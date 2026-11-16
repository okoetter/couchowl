import pytest

from scripts.release_check import ROOT, ReleaseError, changelog_section, release_notes

CHANGELOG = """\
# Changelog

## [Unreleased]

### Added
- Something new

## [1.0.0-rc.1] - 2026-11-20

### Added
- Batch import

## [0.1.0] - 2026-11-06

### Added
- First version

[Unreleased]: https://github.com/okoetter/couchowl/compare/v1.0.0-rc.1...HEAD
"""


def test_notes_are_the_changelog_section_plus_image():
    notes = release_notes("v1.0.0-rc.1", "1.0.0-rc.1", CHANGELOG)
    assert notes.startswith("### Added\n- Batch import\n\n")
    assert "First version" not in notes
    assert "`ghcr.io/okoetter/couchowl:1.0.0-rc.1`" in notes


def test_last_section_stops_at_link_references():
    assert changelog_section(CHANGELOG, "0.1.0") == "### Added\n- First version"


@pytest.mark.parametrize("tag", ["1.0.0", "v1.0", "v1.0.0rc1", "release-1.0.0", "v1.0.0-"])
def test_rejects_malformed_tags(tag):
    with pytest.raises(ReleaseError, match="doesn't look like"):
        release_notes(tag, "1.0.0", CHANGELOG)


def test_rejects_version_mismatch():
    with pytest.raises(ReleaseError, match=r"pyproject\.toml \(0\.1\.0\)"):
        release_notes("v1.0.0-rc.1", "0.1.0", CHANGELOG)


def test_rejects_missing_section():
    with pytest.raises(ReleaseError, match=r"no section"):
        release_notes("v1.0.0", "1.0.0", CHANGELOG)


def test_rejects_empty_section():
    changelog = "## [1.0.0] - 2026-12-01\n\n## [0.1.0] - 2026-11-06\n- x\n"
    with pytest.raises(ReleaseError, match="empty"):
        release_notes("v1.0.0", "1.0.0", changelog)


def test_current_changelog_has_a_section_for_the_current_version():
    """Catches a version bump in pyproject.toml without a CHANGELOG section."""
    import tomllib

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = tomllib.loads(pyproject)["project"]["version"]
    changelog_section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version)
