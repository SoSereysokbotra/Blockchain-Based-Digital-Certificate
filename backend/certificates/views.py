"""
Certificate endpoints.

Organisation scoping (NFR-1.5) is enforced in `get_queryset` on every
authenticated view, never by trusting a URL parameter. A view that looked a
certificate up by ID alone would let one organisation read, revoke or retry
another's records by guessing an identifier.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Certificate, CertificateStatus, RevocationLog
from .serializers import (
    CertificateCreatedSerializer,
    CertificateCreateSerializer,
    CertificateDetailSerializer,
    CertificateListSerializer,
    RevocationSerializer,
)
from .services import CertificateService

logger = logging.getLogger(__name__)


class CertificatePagination(PageNumberPagination):
    page_size = 25  # NFR-2.2
    page_size_query_param = 'page_size'
    max_page_size = 100


class OrganizationScopedMixin:
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        The single choke point for tenant isolation.

        Filtering here rather than in each handler means a new endpoint added
        later inherits the scoping instead of having to remember it.
        """
        return Certificate.objects.filter(
            organization=self.request.user
        ).select_related('organization', 'revocation')

    def get_certificate(self, certificate_id):
        # 404, not 403: confirming that an ID exists but belongs to someone
        # else is itself a disclosure.
        return get_object_or_404(self.get_queryset(), certificate_id=certificate_id)


class CertificateListCreateView(OrganizationScopedMixin, APIView):
    """GET: FR-3.1/FR-3.2 list and search. POST: FR-2.1 create."""

    def get(self, request):
        queryset = self.get_queryset()

        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(recipient_name__icontains=search)
                | Q(certificate_id__icontains=search)
                | Q(course_title__icontains=search)
                | Q(recipient_email__icontains=search)
            )

        status_filter = request.query_params.get('status', '').strip().upper()
        if status_filter in CertificateStatus.values:
            queryset = queryset.filter(status=status_filter)

        paginator = CertificatePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = CertificateListSerializer(
            page, many=True, context={'request': request}
        )
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = CertificateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = CertificateService(request.user)
        certificate, created = service.create(
            serializer.validated_data,
            idempotency_key=request.headers.get('Idempotency-Key'),
        )

        if created:
            # 202, not 201: the certificate is not usable until the on-chain
            # anchor confirms (FR-2.7).
            service.enqueue_issuance(certificate)

        body = CertificateCreatedSerializer(
            certificate, context={'request': request}
        ).data
        return Response(body, status=status.HTTP_202_ACCEPTED)


class CertificateDetailView(OrganizationScopedMixin, APIView):
    """FR-3.3 — full detail including the blockchain reference."""

    def get(self, request, certificate_id):
        certificate = self.get_certificate(certificate_id)
        return Response(
            CertificateDetailSerializer(certificate, context={'request': request}).data
        )


class CertificateRevokeView(OrganizationScopedMixin, APIView):
    """FR-3.4, FR-3.5 — begin revocation."""

    def post(self, request, certificate_id):
        certificate = self.get_certificate(certificate_id)

        serializer = RevocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if certificate.status == CertificateStatus.REVOKED:
            return Response(
                {'detail': 'This certificate is already revoked.'},
                status=status.HTTP_409_CONFLICT,
            )
        if certificate.status in (CertificateStatus.PENDING, CertificateStatus.FAILED):
            # Nothing is anchored yet, so there is nothing on-chain to revoke.
            return Response(
                {'detail': 'This certificate has not been anchored yet and '
                           'cannot be revoked. Wait for issuance to complete.'},
                status=status.HTTP_409_CONFLICT,
            )

        RevocationLog.objects.update_or_create(
            certificate=certificate,
            defaults={
                'revoked_by': request.user,
                'reason': serializer.validated_data['reason'],
                'confirmed_on_chain': False,
                'failure_reason': '',
            },
        )

        from django_q.tasks import async_task

        async_task('certificates.tasks.process_revocation', certificate.certificate_id)

        return Response(
            {'detail': 'Revocation submitted. The certificate will show as '
                       'revoked once the transaction confirms.',
             'status': certificate.status},
            status=status.HTTP_202_ACCEPTED,
        )


class CertificateRetryView(OrganizationScopedMixin, APIView):
    """FR-2.9 — retry a FAILED or stale-PENDING issuance."""

    def post(self, request, certificate_id):
        certificate = self.get_certificate(certificate_id)

        if not certificate.is_retryable:
            if certificate.status == CertificateStatus.PENDING:
                detail = (
                    'This certificate is still being processed. It only becomes '
                    f'retryable after {settings.STALE_PENDING_MINUTES} minutes.'
                )
            else:
                detail = (
                    f'Only failed or stalled certificates can be retried '
                    f'(this one is {certificate.status}).'
                )
            return Response({'detail': detail}, status=status.HTTP_409_CONFLICT)

        certificate.status = CertificateStatus.PENDING
        certificate.failure_reason = ''
        certificate.save(update_fields=['status', 'failure_reason', 'updated_at'])

        # Regenerate the PDF if the earlier attempt never produced one.
        if not certificate.pdf_url:
            CertificateService.attach_pdf(certificate)

        CertificateService.enqueue_issuance(certificate)

        return Response(
            {'detail': 'Retry submitted.', 'status': certificate.status},
            status=status.HTTP_202_ACCEPTED,
        )


class CertificateResendNotificationView(OrganizationScopedMixin, APIView):
    """FR-6.3 — manual resend of issuance notification email."""

    def post(self, request, certificate_id):
        certificate = self.get_certificate(certificate_id)

        if certificate.status != CertificateStatus.VALID:
            return Response(
                {'detail': f'Cannot send notification for a {certificate.status} certificate.'},
                status=status.HTTP_409_CONFLICT,
            )

        from django_q.tasks import async_task

        async_task('notifications.tasks.send_certificate_issued', certificate.certificate_id)

        return Response(
            {'detail': 'Resend requested. The email has been queued.'},
            status=status.HTTP_202_ACCEPTED,
        )
