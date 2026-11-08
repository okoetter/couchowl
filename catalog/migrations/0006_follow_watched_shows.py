from django.db import migrations
from django.utils import timezone


def follow_watching_shows(apps, schema_editor):
    """Shows being watched now follow automatically; without this they would disappear
    from the dashboard, which only shows followed shows."""
    UserSeries = apps.get_model("catalog", "UserSeries")
    UserSeries.objects.filter(status="watching", following=False).update(
        following=True, followed_at=timezone.now()
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_clear_season_placeholders"),
    ]

    operations = [
        migrations.RunPython(follow_watching_shows, migrations.RunPython.noop),
    ]
