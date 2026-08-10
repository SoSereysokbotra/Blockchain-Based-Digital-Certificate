import traceback
from django.utils import timezone
from .models import Certificate, CertificateStatus
from .pipeline import (
    compute_certificate_hash,
    generate_pdf,
    submit_blockchain_tx,
    send_issuance_email,
)


def issue_certificate(certificate_id: str):
    """
    Async task to orchestrate certificate issuance.
    Handles hash generation, PDF creation, blockchain TX, and email.
    """
    try:
        cert = Certificate.objects.get(certificate_id=certificate_id)
    except Certificate.DoesNotExist:
        print(f"Error: Certificate {certificate_id} not found for issuance.")
        return

    if cert.status != CertificateStatus.PENDING:
        print(f"Error: Certificate {certificate_id} is not PENDING (status: {cert.status}).")
        return

    try:
        # Step 1: Hash
        cert_hash = compute_certificate_hash(cert)
        cert.certificate_hash = cert_hash
        
        # Step 2 & 3: PDF Generation
        pdf_path = generate_pdf(cert)
        cert.pdf_url = pdf_path
        
        # Step 4: Blockchain Transaction
        # This blocks until the transaction is confirmed (or fails)
        tx_hash = submit_blockchain_tx(cert.certificate_id, cert_hash)
        cert.blockchain_tx_hash = tx_hash

        # Update status to VALID
        cert.status = CertificateStatus.VALID
        cert.save()
        
        # Step 5: Email Notification
        try:
            send_issuance_email(cert)
        except Exception as e:
            # We don't fail the certificate if email fails, but we should log it
            print(f"Error sending email for {certificate_id}: {e}")

    except Exception as e:
        print(f"Error issuing certificate {certificate_id}: {e}")
        traceback.print_exc()
        cert.status = CertificateStatus.FAILED
        cert.save(update_fields=['status', 'updated_at'])


def revoke_on_chain(certificate_id: str):
    """
    Async task to submit the revocation transaction to the blockchain.
    Assumes the database status is already REVOKED.
    """
    try:
        cert = Certificate.objects.get(certificate_id=certificate_id)
    except Certificate.DoesNotExist:
        print(f"Error: Certificate {certificate_id} not found for revocation.")
        return

    from web3 import Web3
    from django.conf import settings

    rpc_url = settings.BLOCKCHAIN_RPC_URL
    contract_address = settings.BLOCKCHAIN_CONTRACT_ADDRESS
    private_key = settings.BLOCKCHAIN_ISSUER_PRIVATE_KEY

    if not all([rpc_url, contract_address, private_key]):
        print("Error: Blockchain settings not configured for revocation.")
        return

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("Error: Cannot connect to blockchain RPC endpoint.")
        return

    abi = [
        {
            'inputs': [
                {'internalType': 'string', 'name': 'certId', 'type': 'string'},
            ],
            'name': 'revokeCertificate',
            'outputs': [],
            'stateMutability': 'nonpayable',
            'type': 'function',
        }
    ]

    account = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=abi
    )

    try:
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.functions.revokeCertificate(certificate_id).build_transaction({
            'from': account.address,
            'nonce': nonce,
            'gas': 100_000,
            'gasPrice': w3.eth.gas_price,
        })

        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        print(f"Successfully revoked {certificate_id} on-chain. TX: {tx_hash.hex()}")
    except Exception as e:
        print(f"Error revoking {certificate_id} on-chain: {e}")
        traceback.print_exc()
