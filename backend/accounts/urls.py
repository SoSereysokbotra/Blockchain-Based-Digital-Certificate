from django.urls import path

from .views import (
    LoginView,
    LogoutView,
    MeView,
    RefreshTokenView,
    RegisterView,
    RequestPasswordResetView,
    ResendEmailVerificationView,
    ResendPasswordResetView,
    ResetPasswordView,
    VerifyEmailView,
    VerifyPasswordResetView,
)

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path(
        'auth/resend-email-verification/',
        ResendEmailVerificationView.as_view(),
        name='resend-email-verification',
    ),

    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/refresh-token/', RefreshTokenView.as_view(), name='refresh-token'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/me/', MeView.as_view(), name='me'),

    path(
        'auth/request-password-reset/',
        RequestPasswordResetView.as_view(),
        name='request-password-reset',
    ),
    path(
        'auth/verify-password-reset/',
        VerifyPasswordResetView.as_view(),
        name='verify-password-reset',
    ),
    path('auth/reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path(
        'auth/resend-password-reset-verification/',
        ResendPasswordResetView.as_view(),
        name='resend-password-reset-verification',
    ),
]
