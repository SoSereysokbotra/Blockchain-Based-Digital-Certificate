from rest_framework.views import APIView
from rest_framework.response import Response

class CertificateListCreateView(APIView):
    def get(self, request):
        return Response({})
        
    def post(self, request):
        return Response({})

class CertificateDetailView(APIView):
    def get(self, request, pk):
        return Response({})

class CertificateRevokeView(APIView):
    def post(self, request, pk):
        return Response({})

class CertificateRetryView(APIView):
    def post(self, request, pk):
        return Response({})

class PublicCertificateVerifyView(APIView):
    def get(self, request, cert_id):
        return Response({})
