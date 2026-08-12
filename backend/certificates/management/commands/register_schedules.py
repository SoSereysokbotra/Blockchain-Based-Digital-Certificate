"""
Install the recurring django-q2 schedules (FR-2.9, FR-4.2.1).

    docker compose run --rm backend python manage.py register_schedules

Idempotent — safe to re-run on every deploy. Schedules live in the database, so
this is how they get there; without it the qcluster runs but never fires the
expiry or stale-PENDING jobs.
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule


SCHEDULES = [
    {
        'name': 'bcip.flag_stale_pending',
        'func': 'certificates.tasks.flag_stale_pending',
        'schedule_type': Schedule.MINUTES,
        'minutes': 10,
        'description': 'FR-2.9 — surface certificates stuck PENDING as retryable.',
    },
    {
        'name': 'bcip.expire_certificates',
        'func': 'certificates.tasks.expire_certificates',
        'schedule_type': Schedule.DAILY,
        'description': 'FR-4.2.1 — move past-expiry certificates to EXPIRED.',
    },
    {
        'name': 'bcip.purge_login_attempts',
        'func': 'accounts.tasks.purge_login_attempts',
        'schedule_type': Schedule.DAILY,
        'description': 'Housekeeping for the LoginAttempt audit log.',
    },
]


class Command(BaseCommand):
    help = 'Create or update the BCIP scheduled tasks.'

    def handle(self, *args, **options):
        for spec in SCHEDULES:
            name = spec.pop('name')
            spec['repeats'] = -1  # forever
            _, created = Schedule.objects.update_or_create(name=name, defaults=spec)
            verb = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'{verb} schedule {name}'))

        self.stdout.write(
            '\nSchedules fire only while `python manage.py qcluster` is running '
            '(the `worker` service in docker-compose).'
        )
