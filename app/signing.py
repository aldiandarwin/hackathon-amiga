"""Approval steps for vouchers: one account per approver, the password re-entered at the moment of approval, an
append-only step log chained from Finance to the Manajer Keuangan, a content hash plus the PDF hash, and the stored
consent text. Vouchers up to amiga-demo-v6 print these steps as non-certified TTE (PP 71/2019 Pasal 60 ayat 4); from
amiga-demo-v7 the printed voucher carries empty boxes for wet signatures and the steps stay as the app's record.
"""

from collections import defaultdict, deque
import hashlib
import json
import secrets
from threading import Lock
import time

REVIEWER_CONSENT = ('Saya sudah mencocokkan data voucher ini dengan dokumen asli dan menyetujuinya sebagai '
                    'Finance Reviewer AMIGA.')
DIRECTOR_CONSENT = ('Saya menyetujui voucher pengeluaran ini sebagai Manajer Keuangan AMIGA. '
                    'Persetujuan dan pembayaran oleh klien tetap dilakukan di luar aplikasi AMIGA.')
# The PIC's statement when submitting to Finance. One source line, so an SOP card can quote it verbatim.
INTAKE_CONSENT = 'Saya sudah mencocokkan data invoice ini dengan dokumen asli dan bertanggung jawab atas isian, nominal, pilihan pajak, dan pendaftaran vendor yang saya ajukan ke Finance AMIGA.'
CODE_ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'  # no 0/O or 1/I, so a code read aloud cannot be misheard


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def content_sha256(payload):
    """The signed content: the frozen voucher payload without its signature block, so a signature can be printed on
    the same payload it signs."""
    return hashlib.sha256(canonical_json({key: value for key, value in payload.items() if key != 'signatures'})).hexdigest()


def new_verification_code():
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(8))


class SignatureGuard:
    """Wrong signing passwords per user, kept in memory like the login limit: five per ten minutes."""

    def __init__(self, limit=5, window_seconds=600):
        self.limit, self.window, self.lock = limit, window_seconds, Lock()
        self.failures = defaultdict(deque)

    def _recent(self, user_id):
        failures, horizon = self.failures[user_id], time.monotonic() - self.window
        while failures and failures[0] < horizon:
            failures.popleft()
        return failures

    def blocked(self, user_id):
        with self.lock:
            return len(self._recent(user_id)) >= self.limit

    def failed(self, user_id):
        with self.lock:
            self._recent(user_id).append(time.monotonic())

    def succeeded(self, user_id):
        # Like the login limit, a good signature forgives earlier typos.
        with self.lock:
            self.failures.pop(user_id, None)
