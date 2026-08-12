"""
PDF and QR generation (FR-2.3, FR-5.2).

Runs inside the Docker image built in Phase 0; WeasyPrint's Pango/Cairo/
GDK-Pixbuf stack is not installed on the host by design.

The QR image is embedded as a base64 data URI rather than a file path so
WeasyPrint never has to resolve anything from disk — that keeps rendering
hermetic and stops a mis-set base_url from producing a certificate with a
silently missing QR code.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
from pathlib import Path

import qrcode
from django.conf import settings
from django.template.loader import render_to_string
from qrcode.constants import ERROR_CORRECT_M

logger = logging.getLogger(__name__)

PDF_SUBDIR = 'pdfs'


def verification_url(certificate_id: str) -> str:
    """The public page a QR scan should land on (FR-5.2)."""
    return f'{settings.FRONTEND_URL}/verify/{certificate_id}'


def generate_qr_png(certificate_id: str) -> bytes:
    """
    QR code encoding the verification URL.

    Error correction level M (~15% recoverable) rather than the default L,
    because these get printed and photographed under bad conditions.
    """
    qr = qrcode.QRCode(
        version=None,           # let it size itself to the URL
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(verification_url(certificate_id))
    qr.make(fit=True)

    image = qr.make_image(fill_color='black', back_color='white')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def qr_data_uri(certificate_id: str) -> str:
    encoded = base64.b64encode(generate_qr_png(certificate_id)).decode('ascii')
    return f'data:image/png;base64,{encoded}'


def render_pdf_bytes(certificate) -> bytes:
    """Render the certificate template to PDF bytes."""
    from weasyprint import HTML

    html = render_to_string('certificates/certificate_pdf.html', {
        'cert': certificate,
        'organization': certificate.organization,
        'qr_data_uri': qr_data_uri(certificate.certificate_id),
        'verification_url': verification_url(certificate.certificate_id),
    })

    return HTML(string=html, base_url=str(settings.MEDIA_ROOT)).write_pdf()


def pdf_path_for(certificate_id: str) -> Path:
    return Path(settings.MEDIA_ROOT) / PDF_SUBDIR / f'{certificate_id}.pdf'


def generate_and_store_pdf(certificate) -> tuple[str, str]:
    """
    Render, write to MEDIA_ROOT and hash.

    Returns (relative_path, pdf_sha256). The digest is of the exact bytes
    written, so a recipient can later confirm the file they hold is the one that
    was generated. It is never anchored on-chain — WeasyPrint output is not
    byte-reproducible (it embeds a creation timestamp and may subset fonts
    differently between runs), so re-rendering and re-hashing would produce a
    different digest for identical data. That is exactly why the anchored hash
    is computed over canonical *data* instead (see hashing.py).
    """
    pdf_bytes = render_pdf_bytes(certificate)

    destination = pdf_path_for(certificate.certificate_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(pdf_bytes)

    digest = '0x' + hashlib.sha256(pdf_bytes).hexdigest()
    relative = f'{PDF_SUBDIR}/{certificate.certificate_id}.pdf'

    logger.info(
        'Rendered PDF for %s (%s bytes) -> %s',
        certificate.certificate_id, len(pdf_bytes), relative,
    )
    return relative, digest
