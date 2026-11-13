"""`manage.py backup`: consistent copy of the SQLite database to BACKUP_DIR.

Runs nightly in the container (docker/crontab). The host backs up BACKUP_DIR.
Restoring: see docs/administration.md. Rules: see core.backups.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core import backups


class Command(BaseCommand):
    help = (
        "Write a consistent copy of the SQLite database to BACKUP_DIR "
        "and keep the newest BACKUP_KEEP copies."
    )

    def handle(self, *args, **options):
        try:
            database = backups.database_path(settings.DATABASES["default"])
            backup, removed = backups.create_backup(
                database, settings.BACKUP_DIR, settings.BACKUP_KEEP
            )
        except backups.BackupError as error:
            raise CommandError(str(error)) from error

        size_mb = backup.stat().st_size / 1_000_000
        self.stdout.write(
            self.style.SUCCESS(f"Backup: {backup} ({size_mb:.1f} MB), {len(removed)} old removed.")
        )
