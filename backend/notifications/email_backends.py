"""
Email backends that reach their provider over HTTPS instead of SMTP.

Render's free instances firewall off outbound ports 25/465/587, so any
smtp.EmailBackend send dies with `[Errno 101] Network is unreachable`
before it ever reaches the provider. Every backend here POSTs to a REST
API on 443, which is not blocked, while keeping the ordinary
django.core.mail interface: callers keep using EmailMultiAlternatives and
switching provider is a matter of EMAIL_BACKEND alone.

Which one to use comes down to sender identity, not features. A provider
will not send from an address nobody has proved they control, and the two
ways of proving it differ sharply in effort:

  ResendAPIBackend    needs a DNS-verified *domain* before it will mail
                      anyone but the account owner. The right end state
                      once BCIP owns a domain.
  BrevoAPIBackend     confirmed sender *address*, 300/day free.
  MailjetAPIBackend   confirmed sender *address*, 6000/month free.
  SendGridAPIBackend  confirmed sender *address*, 100/day free.

The last three need no domain: you click a link in the sender inbox and
can then mail anyone.
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

    Subclasses supply the endpoint, credentials, the provider's payload
    shape, and how to read a message id back out of a success response.
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

    def auth(self):
        """Credentials for requests' `auth=`, when a header is not enough."""
        return None

    def message_id(self, response):
        """Provider's handle for the queued message, or None."""
        return None

    def error_detail(self, response):
        """
        Provider-level failure reported under a 2xx status.

        Mailjet answers 200 for a per-message rejection, so a status check
        alone would log a send that never happened as a success.
        """
        return None

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
                auth=self.auth(),
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
            return self._fail(f'{self.name} returned {response.status_code}: '
                              f'{response.text[:500]}')

        detail = self.error_detail(response)
        if detail:
            return self._fail(f'{self.name} rejected the message: {detail}')

        # Acceptance is not delivery; the id is the only handle for chasing a
        # later bounce in the Render logs.
        logger.info('%s accepted mail to %s (id=%s)',
                    self.name, message.to, self.message_id(response))
        return True

    def _fail(self, error: str) -> bool:
        if not self.fail_silently:
            raise RuntimeError(error)
        logger.error('%s', error)
        return False

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
    def json_body(response):
        try:
            return response.json()
        except ValueError:
            return {}

    @staticmethod
    def encoded_attachments(message):
        """Yield (filename, mimetype, base64 content) for each attachment."""
        for attachment in message.attachments:
            if isinstance(attachment, tuple):
                filename, content, mimetype = attachment
            else:  # a MIMEBase added via EmailMessage.attach()
                filename = attachment.get_filename()
                content = attachment.get_payload(decode=True)
                mimetype = attachment.get_content_type()
            if content is None:
                continue
            if isinstance(content, str):
                content = content.encode('utf-8')
            yield (filename or 'attachment',
                   mimetype or 'application/octet-stream',
                   base64.b64encode(content).decode('ascii'))


class ResendAPIBackend(_HTTPEmailBackend):
    """https://resend.com/docs/api-reference/emails/send-email"""

    name = 'Resend'
    endpoint = 'https://api.resend.com/emails'
    api_key_setting = 'RESEND_API_KEY'

    def headers(self):
        return {'Authorization': f'Bearer {self.api_key}'}

    def message_id(self, response):
        return self.json_body(response).get('id')

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
            for name, _mimetype, content in self.encoded_attachments(message)
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

    def message_id(self, response):
        return self.json_body(response).get('messageId')

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
        payload['htmlContent'] = self.html_body(message) or f'<pre>{message.body}</pre>'

        attachments = [
            {'name': name, 'content': content}
            for name, _mimetype, content in self.encoded_attachments(message)
        ]
        if attachments:
            payload['attachment'] = attachments
        return payload


class MailjetAPIBackend(_HTTPEmailBackend):
    """https://dev.mailjet.com/email/guides/send-api-v31/"""

    name = 'Mailjet'
    endpoint = 'https://api.mailjet.com/v3.1/send'
    api_key_setting = 'MAILJET_API_KEY'

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.secret_key = getattr(settings, 'MAILJET_SECRET_KEY', '')

    def headers(self):
        return {'Content-Type': 'application/json'}

    def auth(self):
        # Mailjet authenticates with the key pair over HTTP Basic, not a
        # bearer token.
        return (self.api_key, self.secret_key)

    def message_id(self, response):
        messages = self.json_body(response).get('Messages') or [{}]
        recipients = messages[0].get('To') or [{}]
        return recipients[0].get('MessageUUID')

    def error_detail(self, response):
        for entry in self.json_body(response).get('Messages') or []:
            if entry.get('Status') != 'success':
                return str(entry.get('Errors') or entry)[:500]
        return None

    def payload(self, message):
        name, address = self.sender(message)
        sender = {'Email': address}
        if name:
            sender['Name'] = name

        entry = {
            'From': sender,
            'To': [{'Email': recipient} for recipient in message.to],
            'Subject': message.subject,
            'TextPart': message.body,
        }
        if message.cc:
            entry['Cc'] = [{'Email': r} for r in message.cc]
        if message.bcc:
            entry['Bcc'] = [{'Email': r} for r in message.bcc]
        if message.reply_to:
            entry['ReplyTo'] = {'Email': parseaddr(message.reply_to[0])[1]}

        html = self.html_body(message)
        if html:
            entry['HTMLPart'] = html

        attachments = [
            {'Filename': name, 'ContentType': mimetype, 'Base64Content': content}
            for name, mimetype, content in self.encoded_attachments(message)
        ]
        if attachments:
            entry['Attachments'] = attachments

        return {'Messages': [entry]}


class SendGridAPIBackend(_HTTPEmailBackend):
    """https://www.twilio.com/docs/sendgrid/api-reference/mail-send"""

    name = 'SendGrid'
    endpoint = 'https://api.sendgrid.com/v3/mail/send'
    api_key_setting = 'SENDGRID_API_KEY'

    def headers(self):
        return {'Authorization': f'Bearer {self.api_key}'}

    def message_id(self, response):
        # SendGrid answers 202 with an empty body; the id is a header.
        return response.headers.get('X-Message-Id')

    def payload(self, message):
        name, address = self.sender(message)
        sender = {'email': address}
        if name:
            sender['name'] = name

        personalization = {'to': [{'email': r} for r in message.to]}
        if message.cc:
            personalization['cc'] = [{'email': r} for r in message.cc]
        if message.bcc:
            personalization['bcc'] = [{'email': r} for r in message.bcc]

        # Order matters to SendGrid: text/plain must precede text/html.
        content = [{'type': 'text/plain', 'value': message.body}]
        html = self.html_body(message)
        if html:
            content.append({'type': 'text/html', 'value': html})

        payload = {
            'personalizations': [personalization],
            'from': sender,
            'subject': message.subject,
            'content': content,
        }
        if message.reply_to:
            payload['reply_to'] = {'email': parseaddr(message.reply_to[0])[1]}

        attachments = [
            {'filename': name, 'type': mimetype, 'content': content_b64,
             'disposition': 'attachment'}
            for name, mimetype, content_b64 in self.encoded_attachments(message)
        ]
        if attachments:
            payload['attachments'] = attachments
        return payload
