from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from certificates.models import Certificate
from certificates.pdf import pdf_path_for
from .models import NotificationLog, NotificationStatus, NotificationKind

logger = logging.getLogger(__name__)


def send_certificate_issued(certificate_id: str) -> bool:
    """
    Send the certificate PDF to the recipient and log the outcome.
    
    This task is triggered automatically when issuance reaches VALID,
    and manually via the resend-notification endpoint.
    """
    certificate = Certificate.objects.filter(certificate_id=certificate_id).first()
    if certificate is None:
        logger.error('send_certificate_issued: no certificate %s', certificate_id)
        return False

    attempt_number = NotificationLog.objects.filter(
        certificate=certificate,
        kind=NotificationKind.CERTIFICATE_ISSUED,
    ).count() + 1

    subject = f'Your Certificate from {certificate.organization.name}'
    
    # Build verification URL
    from certificates.pdf import verification_url
    url = verification_url(certificate.certificate_id)
    
    body = (
        f'Hello {certificate.recipient_name},\n\n'
        f'You have been issued a certificate for "{certificate.course_title}" by '
        f'{certificate.organization.name}.\n\n'
        f'Your certificate ID is: {certificate.certificate_id}\n\n'
        f'You can view and verify your certificate online at:\n{url}\n\n'
        f'A PDF copy of your certificate is attached to this email.\n'
    )

    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[certificate.recipient_email],
    )

    # Attach PDF
    pdf_path = pdf_path_for(certificate.certificate_id)
    has_attachment = False
    if pdf_path.exists():
        with open(pdf_path, 'rb') as f:
            message.attach(f'{certificate.certificate_id}.pdf', f.read(), 'application/pdf')
            has_attachment = True
    else:
        logger.warning('PDF not found at %s for email attachment', pdf_path)

    try:
        message.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001
        logger.error('Failed to send certificate %s to %s: %s', 
                     certificate.certificate_id, certificate.recipient_email, exc)
        NotificationLog.objects.create(
            certificate=certificate,
            kind=NotificationKind.CERTIFICATE_ISSUED,
            recipient_email=certificate.recipient_email,
            subject=subject,
            status=NotificationStatus.FAILED,
            error_message=str(exc)[:2000],
            has_attachment=has_attachment,
            attempt=attempt_number,
        )
        return False

    logger.info('Sent certificate %s to %s', certificate.certificate_id, certificate.recipient_email)
    NotificationLog.objects.create(
        certificate=certificate,
        kind=NotificationKind.CERTIFICATE_ISSUED,
        recipient_email=certificate.recipient_email,
        subject=subject,
        status=NotificationStatus.SENT,
        has_attachment=has_attachment,
        attempt=attempt_number,
    )
    return True
