"""Check a release tag before anything is published, and print the release notes.

    uv run python scripts/release_check.py v1.2.3 > release-notes.md

Fails (exit code 1) unless
- the tag looks like v1.2.3 or v1.2.3-rc.1 (Semantic Versioning with a "v" prefix),
- the version in pyproject.toml is exactly the tag without "v",
- CHANGELOG.md has a section "## [1.2.3] - YYYY-MM-DD" with some content.

The release notes are that CHANGELOG section plus the image name.
Used by .github/workflows/release.yml.
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "ghcr.io/okoetter/couchowl"
TAG = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:-(?P<pre>[0-9A-Za-z.-]+))?)$")


class ReleaseError(Exception):
    pass


def changelog_section(changelog: str, version: str) -> str:
    """The body of the section for `version` (without its heading), stripped."""
    heading = re.compile(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", re.M)
    match = heading.search(changelog)
    if not match:
        raise ReleaseError(f'CHANGELOG.md has no section "## [{version}] - YYYY-MM-DD".')
    rest = changelog[match.end() :]
    # The section ends at the next version heading or the link references at the bottom
    end = re.search(r"^(## |\[[^\]]+\]: )", rest, re.M)
    body = rest[: end.start() if end else len(rest)].strip()
    if not body:
        raise ReleaseError(f"The CHANGELOG.md section for {version} is empty.")
    return body


def release_notes(tag: str, project_version: str, changelog: str) -> str:
    match = TAG.match(tag)
    if not match:
        raise ReleaseError(f"Tag {tag!r} doesn't look like v1.2.3 or v1.2.3-rc.1.")
    version = match["version"]
    if project_version != version:
        raise ReleaseError(
            f"Tag {tag} doesn't match the version in pyproject.toml ({project_version})."
        )
    body = changelog_section(changelog, version)
    return f"{body}\n\n**Docker image:** `{IMAGE}:{version}` (linux/amd64, linux/arm64)\n"


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <tag>", file=sys.stderr)
        return 2
    with (ROOT / "pyproject.toml").open("rb") as f:
        project_version = tomllib.load(f)["project"]["version"]
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    try:
        print(release_notes(sys.argv[1], project_version, changelog), end="")
    except ReleaseError as error:
        print(f"Release check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
