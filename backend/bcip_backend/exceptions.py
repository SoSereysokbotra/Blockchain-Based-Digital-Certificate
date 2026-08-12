"""
Project-wide DRF exception handling.

Exists mainly for one reason: django-ratelimit signals a breach by raising
`Ratelimited`, which DRF's default handler does not recognise and turns into a
500. Every rate-limited endpoint would therefore report "server error" instead
of 429, and the SRS 3.1.4 limits would be untestable.
"""
from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

try:
    from django_ratelimit.exceptions import Ratelimited
except ImportError:  # pragma: no cover - django-ratelimit is a hard dependency
    Ratelimited = None


def bcip_exception_handler(exc, context):
    if Ratelimited is not None and isinstance(exc, Ratelimited):
        return Response(
            {
                'detail': 'Too many requests. Please wait and try again.',
                'code': 'rate_limited',
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # django-ratelimit raises PermissionDenied in some configurations; only
    # reinterpret it when it is genuinely a rate-limit signal.
    if isinstance(exc, PermissionDenied) and getattr(exc, 'ratelimited', False):
        return Response(
            {'detail': 'Too many requests. Please wait and try again.',
             'code': 'rate_limited'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if isinstance(exc, Http404):
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    return drf_exception_handler(exc, context)
