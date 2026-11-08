"""`manage.py sync_tmdb`: reload followed and watched shows from TMDB.

Runs daily in the container (docker/crontab). Rules: see catalog.sync.
"""

from django.core.management.base import BaseCommand, CommandError

from catalog import sync, tmdb


class Command(BaseCommand):
    help = (
        "Reload all shows that someone follows or watches from TMDB "
        "(new seasons and episodes, air dates, streaming providers)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help=f"Also reload shows loaded within the last {sync.MAX_AGE} (h:mm:ss).",
        )

    def handle(self, *args, force=False, **options):
        verbose = options["verbosity"] >= 2
        try:
            result = sync.sync_shows(
                max_age=None if force else sync.MAX_AGE,
                progress=self.stdout.write if verbose else None,
            )
        except tmdb.TMDBNotConfigured as error:
            raise CommandError("TMDB_API_TOKEN is not set.") from error

        for name in result.failed:
            self.stderr.write(f"Failed: {name}")
        summary = (
            f"TMDB sync: {len(result.updated)} updated, {len(result.skipped)} skipped "
            f"(loaded recently), {len(result.failed)} failed."
        )
        self.stdout.write(self.style.SUCCESS(summary) if not result.failed else summary)
