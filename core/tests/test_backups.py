import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from core import backups


@pytest.fixture
def database(tmp_path) -> Path:
    path = tmp_path / "db.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE lists (name TEXT)")
        connection.execute("INSERT INTO lists VALUES ('Watchlist')")
    connection.close()
    return path


@pytest.fixture
def backup_dir(tmp_path) -> Path:
    return tmp_path / "backups"


def at(monkeypatch, *args):
    """Let the backup believe it is the given (local) time."""
    moment = timezone.make_aware(datetime(*args))
    monkeypatch.setattr(timezone, "localtime", lambda: moment)


def test_backup_is_a_complete_copy(database, backup_dir, monkeypatch):
    at(monkeypatch, 2026, 11, 13, 3, 0, 0)

    backup, removed = backups.create_backup(database, backup_dir, keep=3)

    assert backup == backup_dir / "couchowl-20261113-030000.sqlite3"
    assert removed == []
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT name FROM lists").fetchall() == [("Watchlist",)]
    connection.close()
    # no temporary files left behind
    assert [p.name for p in backup_dir.iterdir()] == [backup.name]


def test_only_the_newest_backups_are_kept(database, backup_dir, monkeypatch):
    created = []
    for day in (10, 11, 12, 13):
        at(monkeypatch, 2026, 11, day, 3, 0, 0)
        backup, removed = backups.create_backup(database, backup_dir, keep=3)
        created.append(backup)

    assert removed == [created[0]]
    assert sorted(backup_dir.iterdir()) == created[1:]


def test_other_files_in_the_backup_dir_are_left_alone(database, backup_dir, monkeypatch):
    backup_dir.mkdir()
    own_copy = backup_dir / "couchowl-before-update.sqlite3"
    own_copy.write_bytes(b"mine")
    at(monkeypatch, 2026, 11, 13, 3, 0, 0)

    backups.create_backup(database, backup_dir, keep=1)
    at(monkeypatch, 2026, 11, 14, 3, 0, 0)
    backups.create_backup(database, backup_dir, keep=1)

    assert own_copy.read_bytes() == b"mine"
    assert len(list(backup_dir.iterdir())) == 2


def test_keep_must_be_positive(database, backup_dir):
    with pytest.raises(backups.BackupError, match="BACKUP_KEEP"):
        backups.create_backup(database, backup_dir, keep=0)


def test_missing_database_is_not_created(tmp_path, backup_dir):
    with pytest.raises(backups.BackupError, match="not found"):
        backups.database_path({"ENGINE": "django.db.backends.sqlite3", "NAME": tmp_path / "x"})

    assert not (tmp_path / "x").exists()


def test_postgresql_points_to_pg_dump():
    with pytest.raises(backups.BackupError, match="pg_dump"):
        backups.database_path({"ENGINE": "django.db.backends.postgresql", "NAME": "couchowl"})


def test_command(database, backup_dir, monkeypatch, settings, capsys):
    settings.BACKUP_DIR = backup_dir
    settings.BACKUP_KEEP = 3
    monkeypatch.setattr(backups, "database_path", lambda config: database)

    call_command("backup")

    assert len(list(backup_dir.glob("couchowl-*.sqlite3"))) == 1
    assert "Backup:" in capsys.readouterr().out


def test_command_reports_errors(monkeypatch):
    def fail(config):
        raise backups.BackupError("For PostgreSQL use pg_dump")

    monkeypatch.setattr(backups, "database_path", fail)

    with pytest.raises(CommandError, match="pg_dump"):
        call_command("backup")
