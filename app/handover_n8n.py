"""The n8n webhook that hands a final voucher to the client's Telegram, for the Hubungi klien page.

Aldian asked on 16 Okt 2026 for the PIC to send the approved voucher to the client through n8n and Telegram. The bot
token stays in n8n. The app only knows the webhook and a shared secret, both in .env, and never retries a send.
"""

from dataclasses import dataclass, field
import logging
from urllib.parse import urlsplit

import httpx

from .settings import ROOT
from amiga_ocr.openai_live import read_dotenv

# n8n answers once Telegram holds the file; a voucher of 70 to 300 KB takes a few seconds. This cuts a hung call.
SEND_SECONDS = 25
LOCAL_HOSTS = ('localhost', '127.0.0.1')
log = logging.getLogger(__name__)


class DeliveryFailed(Exception):
    """Telegram did not confirm the voucher. uncertain: the call was cut after it left, so it may have arrived."""

    def __init__(self, detail, uncertain=False):
        super().__init__(detail)
        self.detail, self.uncertain = detail, uncertain


@dataclass(frozen=True)
class HandoverConfig:
    webhook_url: str
    secret: str = field(repr=False)

    @classmethod
    def load(cls, path=ROOT / '.env'):
        """None while .env does not name the webhook; the page then lists vouchers without sending."""
        values = read_dotenv(path) if path.is_file() else {}
        url = values.get('AMIGA_N8N_VOUCHER_WEBHOOK_URL', '').strip()
        secret = values.get('AMIGA_N8N_WEBHOOK_SECRET', '').strip()
        if not url or not secret:
            return None
        parts = urlsplit(url)
        # Plain http only to a local n8n; anywhere else the voucher would cross the network unencrypted.
        if not parts.hostname or not (parts.scheme == 'https' or (parts.scheme == 'http' and parts.hostname in LOCAL_HOSTS)):
            raise ValueError('AMIGA_N8N_VOUCHER_WEBHOOK_URL must use https, or http to a local n8n.')
        if any(c.isspace() for c in secret):
            raise ValueError('AMIGA_N8N_WEBHOOK_SECRET must not contain spaces.')
        return cls(url, secret)


class N8nSender:
    def __init__(self, config, transport=None):
        self.config = config
        self.http = httpx.Client(transport=transport, follow_redirects=False, headers={'X-Amiga-Secret': config.secret})

    def close(self):
        self.http.close()

    def send(self, payload):
        """The Telegram message id once n8n confirms the file arrived. No retry: a second call could send it twice."""
        try:
            response = self.http.post(self.config.webhook_url, json=payload,
                                      timeout=httpx.Timeout(SEND_SECONDS, connect=5))
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            raise DeliveryFailed(type(error).__name__) from None
        except httpx.TimeoutException as error:
            raise DeliveryFailed(type(error).__name__, uncertain=True) from None
        except httpx.HTTPError as error:
            raise DeliveryFailed(type(error).__name__) from None
        if response.status_code != 200:
            log.warning('n8n HTTP %s: %s', response.status_code, response.text[:300])
            # A gateway that gave up waiting cannot tell whether the workflow went on and sent it.
            raise DeliveryFailed(f'HTTP {response.status_code}', uncertain=response.status_code == 504)
        try:
            body = response.json()
        except ValueError:
            raise DeliveryFailed('not JSON') from None
        message_id = body.get('message_id') if isinstance(body, dict) and body.get('ok') is True else None
        if message_id in (None, ''):
            raise DeliveryFailed('no message id')
        return str(message_id)
