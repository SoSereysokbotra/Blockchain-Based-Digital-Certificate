from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q

from .models import Certificate, CertificateStatus, RevocationLog
from .serializers import (
    CertificateListSerializer,
    CertificateDetailSerializer,
    CertificateCreateSerializer,
    RevocationSerializer,
    PublicVerifySerializer,
)


class CertificatePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class CertificateListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List certificates for the authenticated organization with optional search."""
        search = request.query_params.get('search', '').strip()
        queryset = Certificate.objects.filter(organization=request.user)

        if search:
            queryset = queryset.filter(
                Q(recipient_name__icontains=search) |
                Q(certificate_id__icontains=search) |
                Q(course_title__icontains=search)
            )

        paginator = CertificatePagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = CertificateListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Create a new certificate (returns 202 PENDING — issuance is async)."""
        serializer = CertificateCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Idempotency-Key handling (FR-2.2.1)
        idempotency_key = request.headers.get('Idempotency-Key')
        if idempotency_key:
            existing = Certificate.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                # Return the same response as the original request
                return Response(
                    {
                        'certificate_id': existing.certificate_id,
                        'status': existing.status,
                        'pdf_url': existing.pdf_url,
                    },
                    status=status.HTTP_202_ACCEPTED
                )

        cert = Certificate(
            organization=request.user,
            recipient_name=serializer.validated_data['recipient_name'],
            recipient_email=serializer.validated_data['recipient_email'],
            course_title=serializer.validated_data['course_title'],
            issue_date=serializer.validated_data['issue_date'],
            expiry_date=serializer.validated_data.get('expiry_date'),
            status=CertificateStatus.PENDING,
            idempotency_key=idempotency_key or None,
        )
        cert.save()

        # TODO Phase 10: enqueue async issuance task (PDF gen + blockchain tx)
        # from django_q.tasks import async_task
        # async_task('certificates.tasks.issue_certificate', cert.certificate_id)

        return Response(
            {
                'certificate_id': cert.certificate_id,
                'status': cert.status,
                'pdf_url': cert.pdf_url,
            },
            status=status.HTTP_202_ACCEPTED
        )


class CertificateDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        cert = get_object_or_404(Certificate, certificate_id=pk, organization=request.user)
        serializer = CertificateDetailSerializer(cert)
        return Response(serializer.data)


class CertificateRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        cert = get_object_or_404(Certificate, certificate_id=pk, organization=request.user)

        if cert.status == CertificateStatus.REVOKED:
            return Response(
                {'detail': 'Certificate is already revoked.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if cert.status == CertificateStatus.PENDING:
            return Response(
                {'detail': 'Cannot revoke a certificate that is still pending issuance.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = RevocationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        cert.status = CertificateStatus.REVOKED
        cert.save(update_fields=['status', 'updated_at'])

        RevocationLog.objects.create(
            certificate=cert,
            reason=serializer.validated_data['reason'],
            revoked_by=request.user,
        )

        # TODO Phase 10: enqueue async blockchain revocation task
        # from django_q.tasks import async_task
        # async_task('certificates.tasks.revoke_on_chain', cert.certificate_id)

        return Response({'detail': 'Revocation initiated.'}, status=status.HTTP_202_ACCEPTED)


class CertificateRetryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        cert = get_object_or_404(Certificate, certificate_id=pk, organization=request.user)

        if cert.status != CertificateStatus.FAILED:
            return Response(
                {'detail': 'Only failed certificates can be retried.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        cert.status = CertificateStatus.PENDING
        cert.save(update_fields=['status', 'updated_at'])

        # TODO Phase 10: enqueue async issuance task again
        # from django_q.tasks import async_task
        # async_task('certificates.tasks.issue_certificate', cert.certificate_id)

        return Response({'detail': 'Retry initiated.'}, status=status.HTTP_202_ACCEPTED)


class PublicCertificateVerifyView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, cert_id):
        try:
            cert = Certificate.objects.select_related('revocation').get(
                certificate_id=cert_id
            )
        except Certificate.DoesNotExist:
            return Response(
                {'detail': 'Certificate not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # TODO Phase 11: recompute hash and compare with on-chain record
        # to detect TAMPERED status.

        serializer = PublicVerifySerializer(cert)
        return Response(serializer.data)
