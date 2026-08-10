"""
Certificate issuance pipeline utilities.

Step 1: compute_certificate_hash   — canonical SHA-256 of cert fields
Step 2: generate_qr_code           — verification URL QR as bytes
Step 3: generate_pdf               — WeasyPrint HTML → PDF saved to media/
Step 4: submit_blockchain_tx       — web3.py → CertificateRegistry.issueCertificate
Step 5: send_issuance_email        — SMTP notification to recipient
"""
import hashlib
import io
import json
import os
import qrcode
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from weasyprint import HTML


# ─── Step 1: Hash ─────────────────────────────────────────────────────────────

def compute_certificate_hash(cert) -> str:
    """
    Compute a deterministic SHA-256 hash over the certificate's canonical fields.
    The hash is over a JSON-serialised dict (keys sorted, no extra whitespace).
    """
    canonical = {
        'certificate_id': cert.certificate_id,
        'recipient_name': cert.recipient_name,
        'recipient_email': cert.recipient_email,
        'course_title': cert.course_title,
        'issue_date': str(cert.issue_date),
        'expiry_date': str(cert.expiry_date) if cert.expiry_date else None,
        'organization_id': str(cert.organization_id),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
    return '0x' + hashlib.sha256(raw.encode('utf-8')).hexdigest()


# ─── Step 2: QR Code ──────────────────────────────────────────────────────────

def generate_qr_code(cert_id: str) -> bytes:
    """Generate a QR code PNG (bytes) pointing at the public verification URL."""
    url = f"{settings.FRONTEND_URL}/verify/{cert_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


# ─── Step 3: PDF ──────────────────────────────────────────────────────────────

def generate_pdf(cert) -> str:
    """
    Render the certificate HTML template to PDF and save to MEDIA_ROOT/pdfs/.
    Returns the relative media path (e.g. 'pdfs/CERT-ABC123.pdf').
    """
    import base64

    qr_bytes = generate_qr_code(cert.certificate_id)
    qr_b64 = base64.b64encode(qr_bytes).decode('utf-8')
    qr_data_uri = f'data:image/png;base64,{qr_b64}'

    verification_url = f"{settings.FRONTEND_URL}/verify/{cert.certificate_id}"

    html_string = render_to_string('certificates/certificate_pdf.html', {
        'cert': cert,
        'qr_data_uri': qr_data_uri,
        'verification_url': verification_url,
    })

    pdf_dir = Path(settings.MEDIA_ROOT) / 'pdfs'
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f'{cert.certificate_id}.pdf'

    HTML(string=html_string, base_url=settings.MEDIA_ROOT).write_pdf(str(pdf_path))

    return f'pdfs/{cert.certificate_id}.pdf'


# ─── Step 4: Blockchain TX ────────────────────────────────────────────────────

def submit_blockchain_tx(cert_id: str, cert_hash: str) -> str:
    """
    Submit issueCertificate(certId, certHash) to the deployed CertificateRegistry contract.
    Returns the transaction hash string ('0x...').
    Raises RuntimeError on failure.
    """
    from web3 import Web3

    rpc_url = settings.BLOCKCHAIN_RPC_URL
    contract_address = settings.BLOCKCHAIN_CONTRACT_ADDRESS
    private_key = settings.BLOCKCHAIN_ISSUER_PRIVATE_KEY

    if not all([rpc_url, contract_address, private_key]):
        raise RuntimeError('Blockchain settings not configured.')

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise RuntimeError('Cannot connect to blockchain RPC endpoint.')

    # Minimal ABI — only what we need
    abi = [
        {
            'inputs': [
                {'internalType': 'string', 'name': 'certId', 'type': 'string'},
                {'internalType': 'bytes32', 'name': 'certHash', 'type': 'bytes32'},
            ],
            'name': 'issueCertificate',
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

    # Convert hex hash string to bytes32
    cert_hash_bytes = bytes.fromhex(cert_hash.removeprefix('0x'))

    nonce = w3.eth.get_transaction_count(account.address)
    tx = contract.functions.issueCertificate(cert_id, cert_hash_bytes).build_transaction({
        'from': account.address,
        'nonce': nonce,
        'gas': 200_000,
        'gasPrice': w3.eth.gas_price,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt.status != 1:
        raise RuntimeError(f'Transaction reverted: {tx_hash.hex()}')

    return '0x' + tx_hash.hex()


# ─── Step 5: Email ────────────────────────────────────────────────────────────

def send_issuance_email(cert) -> None:
    """Send a notification email to the certificate recipient."""
    verification_url = f"{settings.FRONTEND_URL}/verify/{cert.certificate_id}"
    pdf_path = Path(settings.MEDIA_ROOT) / cert.pdf_url

    subject = f'Your certificate: {cert.course_title}'
    body = render_to_string('certificates/email_issuance.html', {
        'cert': cert,
        'verification_url': verification_url,
    })

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[cert.recipient_email],
    )
    email.content_subtype = 'html'

    if pdf_path.exists():
        email.attach_file(str(pdf_path))

    email.send(fail_silently=False)
