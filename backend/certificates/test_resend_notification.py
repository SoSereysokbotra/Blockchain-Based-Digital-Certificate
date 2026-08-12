import pytest
from rest_framework import status
from django.urls import reverse
from unittest.mock import patch

from certificates.models import CertificateStatus

@pytest.mark.django_db
def test_resend_notification_success(auth_client, valid_certificate):
    with patch('django_q.tasks.async_task') as mock_async_task:
        url = reverse('certificate-resend-notification', args=[valid_certificate.certificate_id])
        response = auth_client.post(url)
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert 'Resend requested' in response.data['detail']
        mock_async_task.assert_called_once_with('notifications.tasks.send_certificate_issued', valid_certificate.certificate_id)


@pytest.mark.django_db
def test_resend_notification_invalid_status(auth_client, valid_certificate):
    with patch('django_q.tasks.async_task') as mock_async_task:
        valid_certificate.status = CertificateStatus.PENDING
        valid_certificate.save()
        
        url = reverse('certificate-resend-notification', args=[valid_certificate.certificate_id])
        response = auth_client.post(url)
        
        assert response.status_code == status.HTTP_409_CONFLICT
        assert 'Cannot send notification' in response.data['detail']
        mock_async_task.assert_not_called()
