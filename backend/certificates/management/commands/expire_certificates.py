"""
Daily expiration job (FR-4.2.1).

    docker compose run --rm backend python manage.py expire_certificates

Runs as a scheduled django-q2 task in normal operation (see `register_schedules`),
but stays a management command so it can be invoked directly by cron or by a
test without going through the queue.
"""
from django.core.management.base import BaseCommand

from certificates.tasks import expire_certificates


class Command(BaseCommand):
    help = 'Transition VALID certificates past their expiry date to EXPIRED.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args, **options):
        if options['dry_run']:
            from django.utils import timezone

            from certificates.models import Certificate, CertificateStatus

            due = Certificate.objects.filter(
                status=CertificateStatus.VALID,
                expiry_date__lt=timezone.now().date(),
            )
            self.stdout.write(f'{due.count()} certificate(s) would be expired:')
            for certificate_id, expiry in due.values_list('certificate_id', 'expiry_date')[:50]:
                self.stdout.write(f'  {certificate_id}  (expired {expiry})')
            return

        count = expire_certificates()
        self.stdout.write(self.style.SUCCESS(f'Expired {count} certificate(s).'))
