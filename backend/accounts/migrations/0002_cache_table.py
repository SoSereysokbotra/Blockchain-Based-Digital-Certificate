"""
Create the database cache table backing CACHES['default'] (NFR-1.10).

Django's DatabaseCache table is normally created by `manage.py createcachetable`,
which is easy to forget on a fresh clone and produces a confusing
ProgrammingError the first time anything touches the cache — including every
rate-limited endpoint. Creating it here means `migrate` alone leaves the project
in a working state.

`createcachetable` is idempotent, so running the management command as well (as
docker-compose does on start) is harmless.
"""
from django.conf import settings
from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command(
        'createcachetable',
        settings.CACHE_TABLE_NAME,
        database=schema_editor.connection.alias,
        verbosity=0,
    )


def drop_cache_table(apps, schema_editor):
    schema_editor.execute(
        f'DROP TABLE IF EXISTS {schema_editor.quote_name(settings.CACHE_TABLE_NAME)}'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
