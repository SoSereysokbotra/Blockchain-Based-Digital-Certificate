from django.urls import path

from .verification import PublicVerifyView
from .views import (
    CertificateDetailView,
    CertificateListCreateView,
    CertificateResendNotificationView,
    CertificateRetryView,
    CertificateRevokeView,
)

urlpatterns = [
    # Organisation portal (authenticated, organisation-scoped).
    path('certificates/', CertificateListCreateView.as_view(), name='certificate-list-create'),
    path(
        'certificates/<str:certificate_id>/',
        CertificateDetailView.as_view(),
        name='certificate-detail',
    ),
    path(
        'certificates/<str:certificate_id>/revoke/',
        CertificateRevokeView.as_view(),
        name='certificate-revoke',
    ),
    path(
        'certificates/<str:certificate_id>/retry/',
        CertificateRetryView.as_view(),
        name='certificate-retry',
    ),
    path(
        'certificates/<str:certificate_id>/resend-notification/',
        CertificateResendNotificationView.as_view(),
        name='certificate-resend-notification',
    ),

    # Public verification (no authentication, GET only — NFR-1.4).
    path(
        'public/verify/<str:certificate_id>/',
        PublicVerifyView.as_view(),
        name='public-verify',
    ),
]
