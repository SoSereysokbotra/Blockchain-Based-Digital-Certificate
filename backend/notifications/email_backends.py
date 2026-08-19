"""
Email backends that do not need SMTP.

Render's free instances firewall off outbound ports 25/465/587, so any
smtp.EmailBackend send fails with `[Errno 101] Network is unreachable`
before it ever reaches the provider. Resend also exposes an HTTPS API on
443, which is not blocked, so this backend speaks that instead while
keeping the ordinary django.core.mail interface — callers keep using
EmailMultiAlternatives and switching is a matter of EMAIL_BACKEND alone.
"""
from __future__ import annotations

import base64
import logging

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = 'https://api.resend.com/emails'


class ResendAPIBackend(BaseEmailBackend):
    """Deliver each message with one POST to the Resend REST API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, 'RESEND_API_KEY', '')
        self.timeout = getattr(settings, 'EMAIL_TIMEOUT', 20)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if not self.fail_silently:
                raise ValueError('RESEND_API_KEY is not set')
            logger.error('RESEND_API_KEY is not set; dropping %s message(s)',
                         len(email_messages))
            return 0

        sent = 0
        for message in email_messages:
            if self._send(message):
                sent += 1
        return sent

    def _send(self, message) -> bool:
        payload = self._payload(message)
        try:
            response = requests.post(
                RESEND_ENDPOINT,
                json=payload,
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            if not self.fail_silently:
                raise
            logger.error('Resend request failed: %s', exc)
            return False

        if response.status_code >= 400:
            # Resend answers errors as JSON; the body carries the real reason
            # (unverified domain, bad key, ...) so surface it rather than a
            # bare status code.
            detail = response.text[:500]
            if not self.fail_silently:
                raise RuntimeError(
                    f'Resend returned {response.status_code}: {detail}'
                )
            logger.error('Resend returned %s: %s', response.status_code, detail)
            return False

        return True

    def _payload(self, message) -> dict:
        payload = {
            'from': message.from_email or settings.DEFAULT_FROM_EMAIL,
            'to': list(message.to),
            'subject': message.subject,
            'text': message.body,
        }
        if message.cc:
            payload['cc'] = list(message.cc)
        if message.bcc:
            payload['bcc'] = list(message.bcc)
        if message.reply_to:
            payload['reply_to'] = list(message.reply_to)

        for content, mimetype in getattr(message, 'alternatives', []):
            if mimetype == 'text/html':
                payload['html'] = content
                break

        attachments = [
            encoded
            for attachment in message.attachments
            if (encoded := self._attachment(attachment)) is not None
        ]
        if attachments:
            payload['attachments'] = attachments

        return payload

    @staticmethod
    def _attachment(attachment):
        """Normalise a Django attachment into Resend's {filename, content}."""
        if isinstance(attachment, tuple):
            filename, content, _mimetype = attachment
        else:  # a MIMEBase instance added via EmailMessage.attach()
            filename = attachment.get_filename()
            content = attachment.get_payload(decode=True)

        if content is None:
            return None
        if isinstance(content, str):
            content = content.encode('utf-8')

        return {
            'filename': filename or 'attachment',
            'content': base64.b64encode(content).decode('ascii'),
        }
