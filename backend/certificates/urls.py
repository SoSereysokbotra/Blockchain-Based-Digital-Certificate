from django.urls import path
from .views import (
    CertificateListCreateView,
    CertificateDetailView,
    CertificateRevokeView,
    CertificateRetryView,
    PublicCertificateVerifyView
)

urlpatterns = [
    path('certificates/', CertificateListCreateView.as_view(), name='certificate-list-create'),
    path('certificates/<str:pk>/', CertificateDetailView.as_view(), name='certificate-detail'),
    path('certificates/<str:pk>/revoke/', CertificateRevokeView.as_view(), name='certificate-revoke'),
    path('certificates/<str:pk>/retry/', CertificateRetryView.as_view(), name='certificate-retry'),
    path('public/verify/<str:cert_id>/', PublicCertificateVerifyView.as_view(), name='public-verify'),
]
