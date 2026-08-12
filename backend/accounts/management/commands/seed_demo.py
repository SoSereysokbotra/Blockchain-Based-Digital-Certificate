"""
Seed a verified demo organisation (Implementation Plan, Phase 2).

    docker compose run --rm backend python manage.py seed_demo
    docker compose run --rm backend python manage.py seed_demo --wallet 0xAbC…

The wallet address should be the deployer address from Phase 1, since that is
the account authorised on the registry contract. If --wallet is omitted the
address is derived from BLOCKCHAIN_ISSUER_PRIVATE_KEY when it is configured.
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Organization

DEFAULT_EMAIL = 'demo@bcip.local'
DEFAULT_NAME = 'BCIP Demo Institute'
DEFAULT_PASSWORD = 'DemoOrg!2026Secure'


class Command(BaseCommand):
    help = 'Create or update a verified demo Organization for development.'

    def add_arguments(self, parser):
        parser.add_argument('--email', default=DEFAULT_EMAIL)
        parser.add_argument('--name', default=DEFAULT_NAME)
        parser.add_argument('--password', default=DEFAULT_PASSWORD)
        parser.add_argument(
            '--wallet',
            default=None,
            help='Issuer wallet address. Defaults to the address derived from '
                 'BLOCKCHAIN_ISSUER_PRIVATE_KEY.',
        )
        parser.add_argument(
            '--superuser',
            action='store_true',
            help='Also grant staff/superuser so this account can open /admin/.',
        )

    def handle(self, *args, **options):
        email = options['email'].lower()
        wallet = options['wallet'] or self._derive_wallet()

        with transaction.atomic():
            org, created = Organization.objects.get_or_create(
                email=email,
                defaults={'name': options['name']},
            )
            org.name = options['name']
            org.is_verified = True   # skip the email round-trip for local dev
            org.is_active = True
            if wallet:
                org.wallet_address = wallet
            if options['superuser']:
                org.is_staff = True
                org.is_superuser = True
            org.set_password(options['password'])
            org.save()

        verb = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{verb} organisation {email}'))
        self.stdout.write(f'  name     : {org.name}')
        self.stdout.write(f'  password : {options["password"]}')
        self.stdout.write(f'  wallet   : {org.wallet_address or "(not set)"}')
        self.stdout.write(f'  verified : {org.is_verified}')

        if not org.wallet_address:
            self.stdout.write(self.style.WARNING(
                '\nNo wallet address set. Pass --wallet or set '
                'BLOCKCHAIN_ISSUER_PRIVATE_KEY, otherwise issuance cannot be '
                'attributed to this organisation.'
            ))

    def _derive_wallet(self):
        key = getattr(settings, 'BLOCKCHAIN_ISSUER_PRIVATE_KEY', '')
        if not key:
            return None
        try:
            from blockchain.service import BlockchainService

            return BlockchainService().issuer_address
        except Exception as exc:  # noqa: BLE001 — seeding must not hard-fail
            self.stdout.write(self.style.WARNING(
                f'Could not derive wallet from private key: {exc}'
            ))
            return None
