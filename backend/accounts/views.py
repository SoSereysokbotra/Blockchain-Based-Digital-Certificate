from rest_framework.views import APIView
from rest_framework.response import Response

class RegisterView(APIView):
    def post(self, request):
        return Response({})

class VerifyEmailView(APIView):
    def post(self, request):
        return Response({})

class LoginView(APIView):
    def post(self, request):
        return Response({})

class RefreshTokenView(APIView):
    def post(self, request):
        return Response({})

class LogoutView(APIView):
    def post(self, request):
        return Response({})

class RequestPasswordResetView(APIView):
    def post(self, request):
        return Response({})

class VerifyPasswordResetView(APIView):
    def post(self, request):
        return Response({})

class ResetPasswordView(APIView):
    def post(self, request):
        return Response({})
