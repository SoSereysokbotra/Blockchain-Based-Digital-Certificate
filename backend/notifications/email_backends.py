"""
Email backends that reach their provider over HTTPS instead of SMTP.

Render's free instances firewall off outbound ports 25/465/587, so any
smtp.EmailBackend send dies with `[Errno 101] Network is unreachable`
before it ever reaches the provider. Both backends here POST to a REST API
on 443, which is not blocked, while keeping the ordinary django.core.mail
interface: callers keep using EmailMultiAlternatives and switching
provider is a matter of EMAIL_BACKEND alone.

Which one to use comes down to sender identity, not features:

  ResendAPIBackend  needs a DNS-verified domain before it will send to
                    anyone but the account owner. Best once BCIP has a
                    real domain.
  BrevoAPIBackend   sends to any recipient once a single sender *address*
                    is confirmed by clicking a link in that inbox, so it
                    works without owning a domain.
"""
from __future__ import annotations

import base64
import logging
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class _HTTPEmailBackend(BaseEmailBackend):
    """
    Shared plumbing: one POST per message, uniform error handling.

    Subclasses supply the endpoint, the auth header, the provider's payload
    shape, and how to pull a message id out of a success response.
    """

    name = 'http'
    endpoint = ''
    api_key_setting = ''

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, self.api_key_setting, '')
        self.timeout = getattr(settings, 'EMAIL_TIMEOUT', 20)

    # ── provider hooks ────────────────────────────────────────────────────
    def headers(self) -> dict:
        raise NotImplementedError

    def payload(self, message) -> dict:
        raise NotImplementedError

    def message_id(self, data):
        raise NotImplementedError

    # ── django.core.mail interface ────────────────────────────────────────
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if not self.fail_silently:
                raise ValueError(f'{self.api_key_setting} is not set')
            logger.error('%s is not set; dropping %s message(s)',
                         self.api_key_setting, len(email_messages))
            return 0

        return sum(1 for message in email_messages if self._send(message))

    def _send(self, message) -> bool:
        try:
            response = requests.post(
                self.endpoint,
                json=self.payload(message),
                headers=self.headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            if not self.fail_silently:
                raise
            logger.error('%s request failed: %s', self.name, exc)
            return False

        if response.status_code >= 400:
            # The body carries the real reason — unverified sender, bad key,
            # quota — so surface it rather than a bare status code.
            detail = response.text[:500]
            if not self.fail_silently:
                raise RuntimeError(
                    f'{self.name} returned {response.status_code}: {detail}'
                )
            logger.error('%s returned %s: %s', self.name, response.status_code, detail)
            return False

        # Acceptance is not delivery; the id is the only handle for chasing a
        # later bounce in the Render logs.
        try:
            message_id = self.message_id(response.json())
        except ValueError:
            message_id = None
        logger.info('%s accepted mail to %s (id=%s)',
                    self.name, message.to, message_id)
        return True

    # ── helpers ───────────────────────────────────────────────────────────
    def sender(self, message):
        """Split "Name <addr@host>" into its parts; name may be empty."""
        return parseaddr(message.from_email or settings.DEFAULT_FROM_EMAIL)

    def html_body(self, message):
        for content, mimetype in getattr(message, 'alternatives', []):
            if mimetype == 'text/html':
                return content
        return None

    @staticmethod
    def encoded_attachments(message):
        for attachment in message.attachments:
            if isinstance(attachment, tuple):
                filename, content, _mimetype = attachment
            else:  # a MIMEBase added via EmailMessage.attach()
                filename = attachment.get_filename()
                content = attachment.get_payload(decode=True)
            if content is None:
                continue
            if isinstance(content, str):
                content = content.encode('utf-8')
            yield (filename or 'attachment',
                   base64.b64encode(content).decode('ascii'))


class ResendAPIBackend(_HTTPEmailBackend):
    """https://resend.com/docs/api-reference/emails/send-email"""

    name = 'Resend'
    endpoint = 'https://api.resend.com/emails'
    api_key_setting = 'RESEND_API_KEY'

    def headers(self):
        return {'Authorization': f'Bearer {self.api_key}'}

    def message_id(self, data):
        return data.get('id')

    def payload(self, message):
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

        html = self.html_body(message)
        if html:
            payload['html'] = html

        attachments = [
            {'filename': name, 'content': content}
            for name, content in self.encoded_attachments(message)
        ]
        if attachments:
            payload['attachments'] = attachments
        return payload


class BrevoAPIBackend(_HTTPEmailBackend):
    """https://developers.brevo.com/reference/sendtransacemail"""

    name = 'Brevo'
    endpoint = 'https://api.brevo.com/v3/smtp/email'
    api_key_setting = 'BREVO_API_KEY'

    def headers(self):
        return {'api-key': self.api_key, 'accept': 'application/json'}

    def message_id(self, data):
        return data.get('messageId')

    def payload(self, message):
        name, address = self.sender(message)
        sender = {'email': address}
        if name:
            sender['name'] = name

        payload = {
            'sender': sender,
            'to': [{'email': recipient} for recipient in message.to],
            'subject': message.subject,
            'textContent': message.body,
        }
        if message.cc:
            payload['cc'] = [{'email': r} for r in message.cc]
        if message.bcc:
            payload['bcc'] = [{'email': r} for r in message.bcc]
        if message.reply_to:
            payload['replyTo'] = {'email': parseaddr(message.reply_to[0])[1]}

        # Brevo rejects a payload with neither htmlContent nor templateId, so
        # fall back to the plain-text body when the message has no HTML
        # alternative of its own.
        html = self.html_body(message)
        payload['htmlContent'] = html or f'<pre>{message.body}</pre>'

        attachments = [
            {'name': name, 'content': content}
            for name, content in self.encoded_attachments(message)
        ]
        if attachments:
            payload['attachment'] = attachments
        return payload
