from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.conf import settings

from .models import Organization, EmailVerificationCode, PasswordResetCode
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    VerifyEmailSerializer,
    RequestPasswordResetSerializer,
    VerifyPasswordResetSerializer,
    ResetPasswordSerializer
)
from .utils import create_email_verification_code, create_password_reset_code

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
REFRESH_COOKIE_NAME = 'refresh_token'


def _set_refresh_cookie(response, refresh_token):
    """Set an HttpOnly refresh token cookie on a response."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=str(refresh_token),
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
        max_age=60 * 60 * 24 * 7,  # 7 days
    )


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        organization = serializer.save()

        # Generate email verification code and (in future) send email
        code = create_email_verification_code(organization)
        # TODO: dispatch async email task via django-q2
        # For now, log it (remove before production)
        print(f'[DEV] Verification code for {organization.email}: {code}')

        return Response(
            {'detail': 'Registration successful. Please check your email to verify your account.'},
            status=status.HTTP_201_CREATED
        )


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data['code']
        try:
            verification = EmailVerificationCode.objects.select_related('organization').get(code=code)
        except EmailVerificationCode.DoesNotExist:
            return Response({'detail': 'Invalid verification code.'}, status=status.HTTP_400_BAD_REQUEST)

        if timezone.now() > verification.expires_at:
            return Response({'detail': 'Verification code has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        org = verification.organization
        org.is_verified = True
        org.save(update_fields=['is_verified'])
        verification.delete()

        return Response({'detail': 'Email verified successfully.'})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        try:
            org = Organization.objects.get(email=email)
        except Organization.DoesNotExist:
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        # Check lockout
        if org.locked_until and timezone.now() < org.locked_until:
            return Response(
                {'detail': 'Account locked. Try again later.'},
                status=status.HTTP_423_LOCKED
            )

        if not org.check_password(password):
            org.failed_login_attempts += 1
            if org.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                from datetime import timedelta
                org.locked_until = timezone.now() + timedelta(minutes=LOCKOUT_MINUTES)
            org.save(update_fields=['failed_login_attempts', 'locked_until'])
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not org.is_verified:
            return Response({'detail': 'Please verify your email before logging in.'}, status=status.HTTP_403_FORBIDDEN)

        # Reset lockout counters on success
        org.failed_login_attempts = 0
        org.locked_until = None
        org.save(update_fields=['failed_login_attempts', 'locked_until'])

        refresh = RefreshToken.for_user(org)
        access_token = str(refresh.access_token)

        response = Response({'access_token': access_token})
        _set_refresh_cookie(response, refresh)
        return response


class RefreshTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            return Response({'detail': 'Refresh token not provided.'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)
        except Exception:
            return Response({'detail': 'Invalid or expired refresh token.'}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response({'access_token': access_token})
        _set_refresh_cookie(response, refresh)
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass  # Already invalid, continue with logout

        response = Response({'detail': 'Logged out successfully.'})
        response.delete_cookie(REFRESH_COOKIE_NAME)
        return response


class RequestPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RequestPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        # Always return 200 to avoid email enumeration
        try:
            org = Organization.objects.get(email=email)
            code = create_password_reset_code(org)
            # TODO: dispatch async email task
            print(f'[DEV] Password reset code for {email}: {code}')
        except Organization.DoesNotExist:
            pass

        return Response({'detail': 'If that email exists, a reset code has been sent.'})


class VerifyPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data['code']
        try:
            reset = PasswordResetCode.objects.get(code=code, used=False)
        except PasswordResetCode.DoesNotExist:
            return Response({'detail': 'Invalid or expired code.'}, status=status.HTTP_400_BAD_REQUEST)

        if timezone.now() > reset.expires_at:
            return Response({'detail': 'Reset code has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'detail': 'Code is valid. Proceed to reset your password.'})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data['code']
        new_password = serializer.validated_data['new_password']

        try:
            reset = PasswordResetCode.objects.select_related('organization').get(code=code, used=False)
        except PasswordResetCode.DoesNotExist:
            return Response({'detail': 'Invalid or expired code.'}, status=status.HTTP_400_BAD_REQUEST)

        if timezone.now() > reset.expires_at:
            return Response({'detail': 'Reset code has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        org = reset.organization
        org.set_password(new_password)
        org.save(update_fields=['password'])

        reset.used = True
        reset.save(update_fields=['used'])

        return Response({'detail': 'Password reset successfully.'})
