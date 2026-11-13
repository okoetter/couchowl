"""Consistent copies of the SQLite database for the host's backup (`manage.py backup`).

watchit only makes the copy; keeping backups safe (other disk, cloud, versions) is the
job of the host, e.g. the NAS backup. Copying a SQLite file while watchit writes to it
can give a broken copy; SQLite's backup API always gives a consistent one.
"""

import contextlib
import re
import sqlite3
from pathlib import Path

from django.utils import timezone

# watchit-20261113-030000.sqlite3; other files in the directory are never touched
BACKUP_NAME = re.compile(r"^watchit-\d{8}-\d{6}\.sqlite3$")


class BackupError(Exception):
    pass


def database_path(database: dict) -> Path:
    """The SQLite file of a DATABASES entry; other databases have their own tools."""
    if not database["ENGINE"].endswith("sqlite3"):
        raise BackupError(
            "Backups are only built in for SQLite. For PostgreSQL use pg_dump, "
            "e.g. docker compose exec db pg_dump -U watchit watchit > watchit.sql"
        )
    path = Path(database["NAME"])
    if not path.is_file():
        raise BackupError(f"Database file not found: {path}")
    return path


def create_backup(database: Path, backup_dir: Path, keep: int) -> tuple[Path, list[Path]]:
    """Copy `database` to `backup_dir` and keep only the newest `keep` backups.

    Returns the new backup and the removed old ones.
    """
    if keep < 1:
        raise BackupError("BACKUP_KEEP must be at least 1.")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"watchit-{stamp}.sqlite3"
    # Write to a hidden temporary file first: the rotation (and the host's backup)
    # never sees a half-written copy
    temp = backup_dir / f".{target.name}.tmp"
    try:
        # Read-only, so a wrong path never creates an empty database
        with (
            contextlib.closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as src,
            contextlib.closing(sqlite3.connect(temp)) as dst,
        ):
            src.backup(dst)
            result = dst.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise BackupError(f"The copy failed the integrity check: {result}")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target, rotate(backup_dir, keep)


def rotate(backup_dir: Path, keep: int) -> list[Path]:
    """Delete all but the newest `keep` backups (by the time stamp in the name)."""
    backups = sorted(p for p in backup_dir.iterdir() if BACKUP_NAME.match(p.name))
    old = backups[:-keep]
    for path in old:
        path.unlink()
    return old
