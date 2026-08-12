import pytest
from datetime import date, timedelta
from django.urls import reverse
from rest_framework import status
from django.core.cache import cache
from unittest.mock import patch

from certificates.models import Certificate, CertificateStatus
from notifications.models import NotificationLog

@pytest.mark.django_db
def test_full_issuance_and_revocation_flow(auth_client, organization):
    with patch('django_q.tasks.async_task') as mock_async_task:
        # 1. Issuance
        issue_payload = {
            'recipient_name': 'Integration Test User',
            'recipient_email': 'integration@example.com',
            'course_title': 'E2E Flow',
            'issue_date': str(date.today()),
            'expiry_date': str(date.today() + timedelta(days=365)),
        }
        
        response = auth_client.post(reverse('certificate-list'), issue_payload, HTTP_IDEMPOTENCY_KEY='1234')
        assert response.status_code == status.HTTP_202_ACCEPTED
        cert_id = response.data['certificate_id']
        
        cert = Certificate.objects.get(certificate_id=cert_id)
        assert cert.status == CertificateStatus.PENDING
        
        # Simulate async blockchain confirmation
        cert.status = CertificateStatus.VALID
        cert.blockchain_tx_hash = '0x123'
        cert.save()
        
        # 2. Verification
        # Clear cache before verifying
        cache.clear()
        
        with patch('certificates.verification.get_contract') as mock_get_contract:
            # (cert_hash, issuer, issued_at, revoked)
            mock_get_contract.return_value.functions.getCertificate.return_value.call.return_value = (
                b'dummyhash', organization.wallet_address, int(date.today().strftime('%s')), False
            )
            
            verify_response = auth_client.get(reverse('certificate-verify', args=[cert_id]))
            assert verify_response.status_code == status.HTTP_200_OK
            assert verify_response.data['status'] == 'VALID'
            
            # 3. Revocation
            revoke_response = auth_client.post(reverse('certificate-revoke', args=[cert_id]), {'reason': 'E2E Testing'})
            assert revoke_response.status_code == status.HTTP_202_ACCEPTED
            
            # Simulate async blockchain revocation
            cert.status = CertificateStatus.REVOKED
            cert.save()
            
            # Update mock to return revoked=True
            mock_get_contract.return_value.functions.getCertificate.return_value.call.return_value = (
                b'dummyhash', organization.wallet_address, int(date.today().strftime('%s')), True
            )
            
            # Clear cache again for verification
            cache.clear()
            verify_response = auth_client.get(reverse('certificate-verify', args=[cert_id]))
            assert verify_response.status_code == status.HTTP_200_OK
            assert verify_response.data['status'] == 'REVOKED'
