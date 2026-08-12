import pytest
from django.core import mail
from unittest.mock import patch
from notifications.models import NotificationLog, NotificationStatus, NotificationKind
from notifications.tasks import send_certificate_issued


@pytest.mark.django_db
def test_send_certificate_issued_success(valid_certificate):
    with patch('notifications.tasks.pdf_path_for') as mock_pdf_path_for:
        # Mock the PDF path so it exists
        mock_pdf_path_for.return_value.exists.return_value = True
        mock_pdf_path_for.return_value.open.return_value.__enter__.return_value.read.return_value = b"pdf_content"

        assert len(mail.outbox) == 0

        success = send_certificate_issued(valid_certificate.certificate_id)
        assert success is True

        # Ensure email is sent
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert valid_certificate.recipient_email in email.to
        assert len(email.attachments) == 1

        # Ensure log is written
        logs = NotificationLog.objects.filter(certificate=valid_certificate)
        assert logs.count() == 1
        log = logs.first()
        assert log.status == NotificationStatus.SENT
        assert log.kind == NotificationKind.CERTIFICATE_ISSUED
        assert log.attempt == 1


@pytest.mark.django_db
def test_send_certificate_issued_not_found():
    success = send_certificate_issued("NONEXISTENT")
    assert success is False
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_send_certificate_issued_failure(valid_certificate):
    with patch('notifications.tasks.pdf_path_for') as mock_pdf_path_for, \
         patch('django.core.mail.EmailMultiAlternatives.send', side_effect=Exception('SMTP Error')):
        mock_pdf_path_for.return_value.exists.return_value = False

        success = send_certificate_issued(valid_certificate.certificate_id)
        assert success is False

        logs = NotificationLog.objects.filter(certificate=valid_certificate)
        assert logs.count() == 1
        log = logs.first()
        assert log.status == NotificationStatus.FAILED
        assert 'SMTP Error' in log.error_message


@pytest.mark.django_db
def test_resend_notification_increments_attempt(valid_certificate):
    with patch('notifications.tasks.pdf_path_for') as mock_pdf_path_for:
        mock_pdf_path_for.return_value.exists.return_value = False

        send_certificate_issued(valid_certificate.certificate_id)
        send_certificate_issued(valid_certificate.certificate_id)

        logs = NotificationLog.objects.filter(certificate=valid_certificate).order_by('sent_at')
        assert logs.count() == 2
        assert logs[0].attempt == 1
        assert logs[1].attempt == 2
