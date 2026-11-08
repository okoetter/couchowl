from django.db import migrations


def clear_placeholders(apps, schema_editor):
    """TMDB's English placeholder ("Season 3") becomes empty: pages show "Staffel 3" etc."""
    SeasonTranslation = apps.get_model("catalog", "SeasonTranslation")
    SeasonTranslation.objects.filter(name__regex=r"^Season [0-9]+$").update(name="")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_title_networks"),
    ]

    operations = [
        migrations.RunPython(clear_placeholders, migrations.RunPython.noop),
    ]
