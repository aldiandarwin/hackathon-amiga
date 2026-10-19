"""Project-local configuration; secrets never enter public responses."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype'))
from amiga_ocr.openai_live import read_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    demo_password: str = field(repr=False)
    data_dir: Path = ROOT / '.appdata'
    schema: str = 'amiga_mvp'
    test_mode: bool = False
    # Stage 6: Bedrock reads first, OpenAI only when Bedrock fails. Either can be changed in .env.
    extraction_provider: str = 'bedrock'
    extraction_fallback: str = 'openai'
    # Stage 8: base of the verification link printed as a QR on signed vouchers, frozen into each signed copy. The
    # demo server listens on loopback and accepts only 127.0.0.1 and localhost (app/run.py, TrustedHostMiddleware),
    # so a phone cannot open the QR, and changing this value alone does not change that. Demo the in-app link instead.
    public_base_url: str = 'http://127.0.0.1:3000'
    proxy_secret: str = field(default='', repr=False)
    secure_cookies: bool = False

    @classmethod
    def load(cls):
        values = read_dotenv(ROOT / '.env')
        # The process environment wins for the reader choice only, so a demo can switch readers at start
        # (e.g. $env:AMIGA_EXTRACTION_FALLBACK='none' before start.ps1) without editing .env.
        reader = os.environ.get('AMIGA_EXTRACTION_PROVIDER') or values.get('AMIGA_EXTRACTION_PROVIDER', 'bedrock')
        fallback = os.environ.get('AMIGA_EXTRACTION_FALLBACK') or values.get('AMIGA_EXTRACTION_FALLBACK', 'openai')
        public = os.environ.get('AMIGA_PUBLIC_BASE_URL') or values.get('AMIGA_PUBLIC_BASE_URL', 'http://127.0.0.1:3000')
        secret = os.environ.get('AMIGA_PROXY_SECRET') or values.get('AMIGA_PROXY_SECRET', '')
        parts = urlsplit(public)
        if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password
                or parts.path not in ('', '/') or parts.query or parts.fragment or public != public.strip()):
            raise ValueError('AMIGA_PUBLIC_BASE_URL must be an HTTP(S) origin.')
        if secret and (len(secret) < 32 or any(not 33 <= ord(c) <= 126 for c in secret) or parts.scheme != 'https'):
            raise ValueError('The remote proxy requires an HTTPS public origin and a secret of at least 32 ASCII characters.')
        return cls(values['AMIGA_DATABASE_URL'], values['AMIGA_DEMO_PASSWORD'],
                   extraction_provider=reader, extraction_fallback=fallback, public_base_url=public.rstrip('/'),
                   proxy_secret=secret, secure_cookies=parts.scheme == 'https')


MAX_PDF_BYTES = 5_000_000
MAX_PAGES = 5
MAX_BATCH_FILES = 5
