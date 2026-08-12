"""
Confirm the Django → Amoy RPC path works (Implementation Plan, Phase 1).

Calls getCertificate with a dummy key and logs the zero-value response, proving
the backend can reach the deployed contract before any certificate logic depends
on it.

    docker compose run --rm backend python manage.py check_chain
    docker compose run --rm backend python manage.py check_chain --cert-id CERT-ABC123
"""
from django.core.management.base import BaseCommand, CommandError

from blockchain.service import BlockchainError, BlockchainService


class Command(BaseCommand):
    help = 'Verify the RPC connection and read a record from CertificateRegistry.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cert-id',
            default='CERT-CONNECTIVITY-PROBE',
            help='Certificate ID to look up. Defaults to one that will not exist.',
        )

    def handle(self, *args, **options):
        service = BlockchainService()

        if not service.is_configured():
            raise CommandError(
                'Blockchain is not configured. Set BLOCKCHAIN_RPC_URL, '
                'BLOCKCHAIN_CONTRACT_ADDRESS and BLOCKCHAIN_ISSUER_PRIVATE_KEY '
                'in backend/.env (see .env.example).'
            )

        try:
            if not service.check_connection():
                raise CommandError(f'Not connected to RPC at {service.rpc_url}')

            w3 = service.w3
            self.stdout.write(self.style.SUCCESS('RPC connected'))
            self.stdout.write(f'  endpoint     : {service.rpc_url}')
            self.stdout.write(f'  chain id     : {w3.eth.chain_id}')
            self.stdout.write(f'  latest block : {w3.eth.block_number}')
            self.stdout.write(f'  contract     : {service.contract_address}')

            issuer = service.issuer_address
            balance_wei = w3.eth.get_balance(issuer)
            balance = w3.from_wei(balance_wei, 'ether')
            self.stdout.write(f'  issuer       : {issuer}')
            self.stdout.write(f'  balance      : {balance} POL')

            authorized = service.is_authorized_issuer()
            style = self.style.SUCCESS if authorized else self.style.ERROR
            self.stdout.write(style(f'  authorised   : {authorized}'))

            cert_id = options['cert_id']
            record = service.get_certificate(cert_id)

            self.stdout.write('')
            self.stdout.write(f'getCertificate(keccak256("{cert_id}")):')
            self.stdout.write(f'  certHash : {record.cert_hash}')
            self.stdout.write(f'  issuer   : {record.issuer}')
            self.stdout.write(f'  issuedAt : {record.issued_at}')
            self.stdout.write(f'  revoked  : {record.revoked}')
            self.stdout.write(f'  exists   : {record.exists}')

            if not record.exists:
                self.stdout.write(self.style.SUCCESS(
                    '\nZero-value struct returned for an unknown ID, exactly as the '
                    'Phase 1 contract tests document. RPC path verified.'
                ))

            if balance_wei == 0:
                self.stdout.write(self.style.WARNING(
                    '\nIssuer balance is zero — reads work but issuance will fail. '
                    'Fund it at https://faucet.polygon.technology'
                ))
            if not authorized:
                self.stdout.write(self.style.WARNING(
                    '\nIssuer is NOT authorised on this contract. Call '
                    'authorizeIssuer() from the deployer before issuing.'
                ))

        except BlockchainError as exc:
            raise CommandError(str(exc)) from exc
