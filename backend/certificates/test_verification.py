import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache
from rest_framework.test import APIClient

from certificates.models import Certificate, CertificateStatus, RevocationLog
from certificates.verification import Outcome, _revoked_key, invalidate_revocation_cache

pytestmark = pytest.mark.django_db

def verify_url(certificate_id):
    return reverse('public-verify', args=[certificate_id])

@pytest.fixture
def mock_chain():
    with patch('certificates.verification.get_service') as mock:
        yield mock

class TestPublicVerification:
    def test_non_get_returns_405(self, api, valid_certificate):
        # NFR-1.4: GET only
        url = verify_url(valid_certificate.certificate_id)
        assert api.post(url).status_code == 405
        assert api.put(url).status_code == 405
        assert api.delete(url).status_code == 405
        assert api.patch(url).status_code == 405
        assert api.get(url).status_code == 200

    def test_tampered_certificate(self, api, valid_certificate, mock_chain):
        # Simulate chain record that exists but hash doesn't match
        service = mock_chain.return_value
        record = MagicMock()
        record.exists = True
        record.cert_hash = '0x' + 'a' * 64  # Different hash
        record.revoked = False
        record.issuer = '0xIssuer'
        record.issued_at = 1234567890
        service.get_certificate.return_value = record

        # Manually alter DB to simulate tampering
        valid_certificate.course_title = "Tampered Title"
        valid_certificate.save()

        response = api.get(verify_url(valid_certificate.certificate_id))
        
        assert response.status_code == 200
        assert response.data['status'] == Outcome.TAMPERED
        assert 'warning' in response.data

    def test_rate_limit(self, api, valid_certificate, mock_chain):
        # 30 req/min limit
        url = verify_url(valid_certificate.certificate_id)
        
        # We need to bypass the actual chain call to be fast, but it's not strictly necessary if cached,
        # but let's mock it anyway to avoid RPC overhead if cache misses
        service = mock_chain.return_value
        record = MagicMock()
        record.exists = True
        record.cert_hash = valid_certificate.certificate_hash
        record.revoked = False
        record.issuer = '0xIssuer'
        record.issued_at = 1234567890
        service.get_certificate.return_value = record

        # Clear cache to ensure clean slate for rate limit
        cache.clear()
        
        client = APIClient()
        # Send 30 requests, they should succeed
        for _ in range(30):
            res = client.get(url)
            assert res.status_code == 200

        # The 31st request should be rate-limited
        res = client.get(url)
        assert res.status_code == 429

    def test_cache_invalidation_on_revocation(self, api, valid_certificate, mock_chain):
        # First read sets the cache
        url = verify_url(valid_certificate.certificate_id)
        
        service = mock_chain.return_value
        record = MagicMock()
        record.exists = True
        record.cert_hash = valid_certificate.certificate_hash
        record.revoked = False
        record.issuer = '0xIssuer'
        record.issued_at = 1234567890
        service.get_certificate.return_value = record

        res = api.get(url)
        assert res.data['status'] == Outcome.VALID
        
        # Verify it's cached
        assert cache.get(_revoked_key(valid_certificate.certificate_id)) is False
        
        # Simulate invalidation
        invalidate_revocation_cache(valid_certificate.certificate_id)
        
        # Cache should be empty for revoked flag
        assert cache.get(_revoked_key(valid_certificate.certificate_id)) is None
        
        # Now if we read again, it should fetch from chain. We change the mock to return revoked=True
        record.revoked = True
        res = api.get(url)
        assert res.data['status'] == Outcome.REVOKED

    def test_load_test(self, api, valid_certificate, mock_chain):
        import time
        from concurrent.futures import ThreadPoolExecutor

        url = verify_url(valid_certificate.certificate_id)

        service = mock_chain.return_value
        record = MagicMock()
        record.exists = True
        record.cert_hash = valid_certificate.certificate_hash
        record.revoked = False
        record.issuer = '0xIssuer'
        record.issued_at = 1234567890
        service.get_certificate.return_value = record
        
        # Warm the cache
        api.get(url)

        # Threaded Django test client requests
        def make_request():
            client = APIClient()
            # use a different IP to avoid rate limit or just clear rate limit cache?
            # Rate limit is 30/min per IP, if we fire 10 concurrent, it's 10 requests, which is under 30.
            start = time.time()
            res = client.get(url)
            duration = time.time() - start
            return res.status_code, duration

        # We will clear the ratelimit cache to be safe
        cache.clear()
        # Rewarm
        api.get(url)

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda _: make_request(), range(10)))

        # all should be 200
        assert all(status == 200 for status, duration in results)
        
        # 95% of requests should be < 3 seconds
        # 95% of 10 is 9.5 -> all 10 must be < 3 seconds
        assert all(duration < 3.0 for status, duration in results)
