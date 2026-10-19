"""Amazon Bedrock (Nova 2 Lite) extraction through Converse tool use, mirroring OpenAIClient's trace and ledger.

Region is locked to ap-southeast-1 because the class account denies Bedrock elsewhere. Credentials come only from
the local .env and never appear in repr, logs, traces or error messages. Every attempt reserves US$0.05 in a
durable ledger before any network call; reservations are never refunded.

Ledger CLI, run from prototype/:
    ..\\.venv\\Scripts\\python.exe -m amiga_ocr.bedrock_live --init-ledger   (one time, refuses an existing file)
    ..\\.venv\\Scripts\\python.exe -m amiga_ocr.bedrock_live --snapshot
"""

import argparse
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import re
import sys
import time

from botocore.config import Config as BotoConfig
from botocore.exceptions import (BotoCoreError, ClientError, ConnectionClosedError, ConnectTimeoutError,
                                 EndpointConnectionError, NoCredentialsError, PartialCredentialsError,
                                 ReadTimeoutError)
from PIL import Image, ImageOps
import pymupdf

from .contracts import METADATA_FIELDS, ContractError, validate_extraction
from .live_budget import BudgetError, BudgetLedger
# _absent is the exact null-string cleanup normalize_payload applies; reused so a diagnosis matches its verdict.
from .openai_live import (MEDIA_TYPES, PROMPT, PROMPT_VERSION, ROOT, LiveError, _absent, extraction_schema,
                          normalize_payload, read_dotenv)

REGION = 'ap-southeast-1'
DEFAULT_MODEL_ID = 'global.amazon.nova-2-lite-v1:0'
# The prices below belong to Nova 2 Lite only (any inference profile prefix). Another model would make every
# cost estimate wrong, so it is refused instead of being billed against the wrong table.
PRICED_MODEL = re.compile(r'(?:[a-z]{2,6}\.)?amazon\.nova-2-lite-v1:0')
LEDGER_PATH = ROOT / 'prototype' / '.local' / 'spend-bedrock.sqlite3'
DEFAULT_STOP_USD = Decimal('2.00')
RESERVATION_MICRO_USD = 50_000
TOOL_NAME = 'simpan_invoice'
TOOL_DESCRIPTION = 'Record the invoice extracted from the attached pages.'
# The shared PROMPT asks for plain decimals but, unlike the spike prompt, gives no example; without one Nova copied
# 4.440.000,00 verbatim into the invoice object (smoke call, 14 Oct 2026). Evidence must stay verbatim.
INSTRUCTION = ('Extract this invoice by calling simpan_invoice exactly once. In the invoice object write every '
               'amount and quantity as a plain decimal with a dot and no grouping: 4.440.000,00 becomes 4440000.00 '
               'and 0,00 becomes 0.00. Evidence raw_value stays exactly as printed. Text layer hints, when present, '
               'come from the same PDF and may be incomplete; the page image is the source of truth.')
AMOUNT_DESCRIPTION = 'Plain decimal, dot separator, no grouping (4.440.000,00 is 4440000.00); null if absent.'
MAX_BYTES = 5_000_000
MAX_PAGES = 5            # Nova 2 Lite takes at most 5 embedded images per request; the app allows 5 pages.
MAX_OUTPUT_TOKENS = 4096
PDF_SCALE = 2.0          # A4 renders at 1190 x 1684 px.
PDF_LONG_SIDE = 2000
IMAGE_LONG_SIDE = 2400
IMAGE_PIXELS_LIMIT = 50_000_000
IMAGE_BYTES_LIMIT = 3_750_000
# Hints are capped in UTF-8 bytes, which also caps their tokens: no tokenizer emits more tokens than bytes.
HINT_BYTES = 5_000
BLOCKING_STATES = ('PENDING', 'UNCERTAIN', 'COST_BREACH')

# Nova 2 Lite, USD per 1M tokens. Third-party calculators list 0.30/2.50 for the global profile and 0.33/2.75 for
# regional profiles; the higher pair is used as an upper bound. Calibration point: Bedrock spike of 14 Oct 2026,
# 2-page PDF plus faktur pajak, 2,728 input / 1,184 output tokens = about US$0.0042 at these rates.
PRICE_INPUT_PER_M = Decimal('0.33')
PRICE_OUTPUT_PER_M = Decimal('2.75')
PRICE_VERIFIED = '2026-10-14'
# Worst request we can send: 5 images at Nova 2's flat 230 tokens each, 5 capped hints, and the system prompt,
# tool schema and labels (measured near 2,000 tokens; 6,000 allowed), answered with a full MAX_OUTPUT_TOKENS reply.
WORST_INPUT_TOKENS = MAX_PAGES * (230 + HINT_BYTES) + 6_000

MONEY_KEYS = ('stated_subtotal', 'stated_discount_total', 'stated_other_charges_total', 'stated_tax_total', 'stated_total')
INVOICE_TEXT_KEYS = ('vendor_name', 'invoice_number', 'invoice_date', 'due_date', 'currency') + MONEY_KEYS \
    + METADATA_FIELDS
PAYMENT_KEYS = ('bank_name', 'account_holder', 'account_number')
ITEM_AMOUNT_KEYS = ('quantity', 'unit_price', 'stated_line_total')
ITEM_KEYS = ('description',) + ITEM_AMOUNT_KEYS
# Comma decimal with 1-2 digits and optional dot grouping in threes: 4.440.000,00 or 0,00. It has no other reading,
# and it is the pattern the app validator already parses in quotes. 1,234 (3 digits) is a thousands group in
# English layouts, so it is left alone for the contract to reject.
DECIMAL_COMMA = re.compile(r'-?(?:\d+|\d{1,3}(?:\.\d{3})+),\d{1,2}')

ACCESS_CODES = {'AccessDeniedException', 'UnrecognizedClientException', 'InvalidSignatureException',
                'ExpiredTokenException', 'IncompleteSignature', 'MissingAuthenticationToken',
                'InvalidClientTokenId', 'SignatureDoesNotMatch', 'UnauthorizedException'}
THROTTLE_CODES = {'ThrottlingException', 'TooManyRequestsException', 'ServiceQuotaExceededException',
                  'ModelNotReadyException', 'ProvisionedThroughputExceededException'}
TIMEOUT_CODES = {'ModelTimeoutException', 'RequestTimeout', 'RequestTimeoutException'}
REASON_TEXT = {'access_denied': 'access denied', 'throttled': 'throttled', 'timeout': 'timeout',
               'invalid_output': 'invalid output', 'budget': 'budget', 'network': 'network failure',
               'request_rejected': 'request rejected', 'service_error': 'service error',
               'client_error': 'client error', 'uncertain': 'outcome unknown', 'invalid_input': 'invalid input'}


class BedrockError(LiveError):
    """LiveError with a short machine reason; the message never carries document or credential values.

    For invalid output, attempt_runs and responses keep the billed attempts. responses hold document values:
    persist them only where traces belong, never in logs."""

    def __init__(self, reason: str, message: str, attempt_runs=None, responses=None):
        super().__init__(message)
        self.reason, self.attempt_runs, self.responses = reason, attempt_runs or [], responses or []


def parse_stop_usd(raw) -> Decimal:
    try:
        stop = DEFAULT_STOP_USD if raw is None or raw == '' else Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        stop = Decimal('NaN')
    if not stop.is_finite() or not Decimal(0) < stop <= Decimal('8'):
        raise LiveError('AMIGA_BEDROCK_STOP_USD must be above 0 and at most 8.')
    return stop


@dataclass(frozen=True)
class BedrockConfig:
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    session_token: str | None = field(default=None, repr=False)
    model_id: str = DEFAULT_MODEL_ID
    stop_usd: Decimal = DEFAULT_STOP_USD
    region: str = REGION

    def __post_init__(self):
        if self.region != REGION:
            raise LiveError('Bedrock is locked to ap-southeast-1; the account denies other regions.')
        if not isinstance(self.model_id, str) or not PRICED_MODEL.fullmatch(self.model_id):
            raise LiveError('Unpriced Bedrock model blocked; only Amazon Nova 2 Lite is priced here.')
        parse_stop_usd(self.stop_usd)
        secrets = [self.secret_access_key] + ([self.session_token] if self.session_token is not None else [])
        if (not isinstance(self.access_key_id, str) or not re.fullmatch(r'[A-Z0-9]{16,128}', self.access_key_id)
                or not all(isinstance(s, str) and s and not any(c.isspace() for c in s) for s in secrets)):
            raise LiveError('AWS credentials missing or malformed in local .env; values hidden.')

    @classmethod
    def load(cls, path=None):
        try:
            values = read_dotenv(ROOT / '.env' if path is None else path)
        except (OSError, UnicodeError):
            raise LiveError('Local .env missing or unreadable; Bedrock disabled. Values hidden.') from None
        return cls.from_values(values)

    @classmethod
    def from_values(cls, values: dict):
        key_id, alias = values.get('AWS_ACCESS_KEY_ID', ''), values.get('AWS_ACCESS_KEY', '')
        if key_id and alias and key_id != alias:
            raise LiveError('AWS_ACCESS_KEY_ID and AWS_ACCESS_KEY differ in .env; keep one. Values hidden.')
        for name in ('AWS_REGION', 'AWS_DEFAULT_REGION'):
            if values.get(name) and values[name] != REGION:
                raise LiveError(f'{name} in .env must be ap-southeast-1; the account denies other regions.')
        return cls(key_id or alias, values.get('AWS_SECRET_ACCESS_KEY', ''), values.get('AWS_SESSION_TOKEN') or None,
                   values.get('AMIGA_BEDROCK_MODEL_ID') or DEFAULT_MODEL_ID,
                   parse_stop_usd(values.get('AMIGA_BEDROCK_STOP_USD')))


def bedrock_schema():
    """Bedrock copy of extraction_schema(). Deliberate differences, all re-checked by normalize_payload:

    Nova documents only type, properties and required for tool schemas, so additionalProperties is dropped at every
    level (the contract still rejects unknown keys). vendor_id is omitted instead of declared {'type': 'null'}: it
    is always null and is added back before validation. Descriptions are added where Nova went wrong on 14 Oct:
    line_number (0-based in the spike) and amounts (copied as 4.440.000,00 in the first smoke call)."""
    def strip(node):
        if isinstance(node, dict):
            return {key: strip(value) for key, value in node.items() if key != 'additionalProperties'}
        return [strip(value) for value in node] if isinstance(node, list) else node
    schema = strip(extraction_schema())
    invoice = schema['properties']['invoice']
    del invoice['properties']['vendor_id']
    invoice['required'] = [key for key in invoice['required'] if key != 'vendor_id']
    item = invoice['properties']['line_items']['items']
    item['properties']['line_number'] = {'type': 'integer',
                                         'description': 'Row position in source order; the first row is 1.'}
    for properties, keys in ((invoice['properties'], MONEY_KEYS), (item['properties'], ITEM_AMOUNT_KEYS)):
        for key in keys:
            properties[key] = {'type': ['string', 'null'], 'description': AMOUNT_DESCRIPTION}
    return schema


def _digest(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def request_profile():
    """Everything besides the shared PROMPT that shapes the answer; recorded with every trace and evaluation."""
    return {'tool': TOOL_NAME, 'tool_choice': 'tool', 'schema_sha256': _digest(bedrock_schema()),
            'instruction_sha256': _digest(INSTRUCTION), 'max_tokens': MAX_OUTPUT_TOKENS, 'temperature': 0,
            'pdf_scale': PDF_SCALE, 'pdf_long_side_px': PDF_LONG_SIDE, 'image_long_side_px': IMAGE_LONG_SIDE,
            'hint_bytes_per_page': HINT_BYTES}


def _rgb(image):
    # Transparent PNG backgrounds would turn black on a plain RGB conversion and hide black text.
    if image.mode in ('RGBA', 'LA', 'PA') or (image.mode == 'P' and 'transparency' in image.info):
        rgba = image.convert('RGBA')
        canvas = Image.new('RGB', rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.getchannel('A'))
        return canvas
    return image.convert('RGB')


def _encode(image, prefer_png: bool):
    # PNG keeps rendered text crisp; a photographic scan can exceed the per-image limit as PNG, so JPEG backs it up.
    for fmt, options in ((('png', {}),) if prefer_png else ()) + (('jpeg', {'quality': 90}),):
        out = io.BytesIO()
        image.save(out, fmt.upper(), **options)
        if out.tell() <= IMAGE_BYTES_LIMIT:
            return fmt, out.getvalue()
    raise BedrockError('invalid_input', 'Page image too large for Bedrock even as JPEG.')


def _hint(text: str):
    text = text.strip()
    raw = text.encode('utf-8')
    if len(raw) > HINT_BYTES:
        text = raw[:HINT_BYTES].decode('utf-8', 'ignore') + '\n[text layer truncated]'
    return text or None


def render_pdf(data: bytes):
    try:
        document = pymupdf.open(stream=data, filetype='pdf')
    except Exception:
        raise BedrockError('invalid_input', 'PDF could not be opened for rendering.') from None
    pages = []
    with document:
        if document.needs_pass:
            raise BedrockError('invalid_input', 'Password-protected PDF refused.')
        if not 1 <= document.page_count <= MAX_PAGES:
            raise BedrockError('invalid_input', 'One invoice must have 1 to 5 pages.')
        try:
            for page in document:
                scale = min(PDF_SCALE, PDF_LONG_SIDE / max(page.rect.width, page.rect.height))
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                image = Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)
                fmt, encoded = _encode(image, prefer_png=True)
                pages.append({'format': fmt, 'bytes': encoded, 'size': image.size, 'hint': _hint(page.get_text())})
        except BedrockError:
            raise
        except Exception:
            raise BedrockError('invalid_input', 'PDF page could not be rendered.') from None
    return pages


def prepare_image(data: bytes, media_type: str):
    try:
        with Image.open(io.BytesIO(data)) as source:
            # Phone cameras often write MPO, a JPEG with extra frames; Pillow reads its first frame.
            if source.format not in (('PNG',) if media_type == 'image/png' else ('JPEG', 'MPO')):
                raise BedrockError('invalid_input', 'Image content does not match its declared type.')
            if source.width * source.height > IMAGE_PIXELS_LIMIT:
                raise BedrockError('invalid_input', 'Image resolution too large.')
            image = _rgb(ImageOps.exif_transpose(source))  # a new image; the uploaded bytes stay untouched
    except BedrockError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise BedrockError('invalid_input', 'Image could not be decoded.') from None
    if max(image.size) > IMAGE_LONG_SIDE:
        image.thumbnail((IMAGE_LONG_SIDE, IMAGE_LONG_SIDE), Image.Resampling.LANCZOS)
    fmt, encoded = _encode(image, prefer_png=media_type == 'image/png')
    return [{'format': fmt, 'bytes': encoded, 'size': image.size, 'hint': None}]


def prepare_pages(data: bytes, media_type: str):
    magic = MEDIA_TYPES.get(media_type)
    if magic is None or not isinstance(data, bytes) or not data.startswith(magic) or len(data) > MAX_BYTES:
        raise BedrockError('invalid_input', 'Expected one PDF, JPEG or PNG no larger than 5 MB.')
    return render_pdf(data) if media_type == 'application/pdf' else prepare_image(data, media_type)


def build_request(model_id: str, pages):
    content = []
    for number, page in enumerate(pages, 1):
        content.append({'text': f'Page {number}:'})
        content.append({'image': {'format': page['format'], 'source': {'bytes': page['bytes']}}})
        if page['hint']:
            content.append({'text': f'Text layer hint for page {number}:\n{page["hint"]}'})
    content.append({'text': INSTRUCTION})
    return {'modelId': model_id, 'system': [{'text': PROMPT}], 'messages': [{'role': 'user', 'content': content}],
            'toolConfig': {'tools': [{'toolSpec': {'name': TOOL_NAME, 'description': TOOL_DESCRIPTION,
                                                   'inputSchema': {'json': bedrock_schema()}}}],
                           'toolChoice': {'tool': {'name': TOOL_NAME}}},
            'inferenceConfig': {'maxTokens': MAX_OUTPUT_TOKENS, 'temperature': 0}}


def usage_cost(usage: dict) -> Decimal:
    """Upper-bound token price, not an AWS bill."""
    return (Decimal(usage['input_tokens']) * PRICE_INPUT_PER_M
            + Decimal(usage['output_tokens']) * PRICE_OUTPUT_PER_M) / 1_000_000


def worst_case_request_usd() -> Decimal:
    return usage_cost({'input_tokens': WORST_INPUT_TOKENS, 'output_tokens': MAX_OUTPUT_TOKENS})


def billable_usage(raw) -> dict:
    """Converse usage as {input_tokens, output_tokens}; cache counters (unused here) are priced as input."""
    if not isinstance(raw, dict):
        raise LiveError('Missing billable usage.')
    inputs = [raw.get('inputTokens'), raw.get('cacheReadInputTokens', 0), raw.get('cacheWriteInputTokens', 0)]
    output = raw.get('outputTokens')
    if any(type(value) is not int or value < 0 for value in inputs + [output]) or output > MAX_OUTPUT_TOKENS:
        raise LiveError('Usage outside priced bounds.')
    return {'input_tokens': sum(inputs), 'output_tokens': output}


def failure_reason(error):
    if isinstance(error, ClientError):
        code = str(((getattr(error, 'response', None) or {}).get('Error') or {}).get('Code') or '')
        code = code if re.fullmatch(r'[A-Za-z0-9.]{1,64}', code) else 'Unknown'
        if code in ACCESS_CODES:
            return 'access_denied', code
        if code in THROTTLE_CODES:
            return 'throttled', code
        if code in TIMEOUT_CODES:
            return 'timeout', code
        return ('request_rejected' if code == 'ValidationException' else 'service_error'), code
    name = type(error).__name__
    if isinstance(error, (ReadTimeoutError, ConnectTimeoutError)):
        return 'timeout', name
    if isinstance(error, (NoCredentialsError, PartialCredentialsError)):
        return 'access_denied', name
    if isinstance(error, (EndpointConnectionError, ConnectionClosedError)):
        return 'network', name
    return 'client_error', name


def tool_input(response):
    """The single simpan_invoice call, or None when it is missing or repeated."""
    content = ((response.get('output') or {}).get('message') or {}).get('content') or []
    calls = [block['toolUse'] for block in content if isinstance(block, dict) and isinstance(block.get('toolUse'), dict)
             and block['toolUse'].get('name') == TOOL_NAME]
    return calls[0].get('input') if len(calls) == 1 and isinstance(calls[0].get('input'), dict) else None


def _blank(value):
    return value is None or (isinstance(value, str) and value.strip().lower() in ('', 'null', 'none'))


def to_contract(raw: dict):
    """Close gaps that carry no document information; never changes a value read from the page.

    vendor_id is added as null (omitted from the Bedrock schema), absent nullable keys become null (absent means
    null in the contract), 0-based row numbers 0..n-1 shift to 1..n (seen in the spike; any other numbering is left
    for the contract to reject), evidence quoting nothing is dropped, and the SAME quote cited again on another page
    keeps only its first citation (a faktur page repeats names and NPWPs; different quotes stay and are rejected as
    ambiguous). Returns the payload and notes."""
    payload, notes = deepcopy(raw), []
    invoice = payload.get('invoice')
    if isinstance(invoice, dict):
        invoice.setdefault('vendor_id', None)  # a non-null model value stays, so the contract rejects it
        missing = [key for key in INVOICE_TEXT_KEYS if key not in invoice]
        payment = invoice.get('payment')
        if isinstance(payment, dict):
            missing += ['payment.' + key for key in PAYMENT_KEYS if key not in payment]
            payment.update({key: None for key in PAYMENT_KEYS if key not in payment})
        invoice.update({key: None for key in INVOICE_TEXT_KEYS if key not in invoice})
        items = invoice.get('line_items')
        if isinstance(items, list) and all(isinstance(item, dict) for item in items):
            for item in items:
                missing += ['line_items[].' + key for key in ITEM_KEYS if key not in item]
                item.update({key: None for key in ITEM_KEYS if key not in item})
            numbers = [item.get('line_number') for item in items]
            if items and all(type(n) is int for n in numbers) and numbers == list(range(len(items))):
                for item in items:
                    item['line_number'] += 1
                notes.append('line_numbers_zero_based_shifted')
        if missing:
            notes.append('missing_keys_as_null:' + ','.join(sorted(set(missing))))
        converted = 0
        targets = [(invoice, MONEY_KEYS)] + [(item, ITEM_AMOUNT_KEYS) for item in
                                             (items if isinstance(items, list) else []) if isinstance(item, dict)]
        for node, keys in targets:
            for key in keys:
                value = node.get(key)
                if isinstance(value, str) and DECIMAL_COMMA.fullmatch(value.strip()):
                    node[key] = value.strip().replace('.', '').replace(',', '.')
                    converted += 1
        if converted:
            notes.append(f'comma_decimals_converted:{converted}')
    evidence = payload.get('evidence')
    if isinstance(evidence, list):
        kept, first, blank, repeated = [], {}, 0, 0
        for entry in evidence:
            if isinstance(entry, dict) and _blank(entry.get('raw_value')):
                blank += 1
                continue
            if isinstance(entry, dict) and isinstance(entry.get('field'), str):
                prior = first.setdefault(entry['field'], entry)
                if prior is not entry and prior.get('raw_value') == entry.get('raw_value'):
                    repeated += 1
                    continue
            kept.append(entry)
        if blank:
            notes.append(f'blank_evidence_dropped:{blank}')
        if repeated:
            notes.append(f'repeated_quote_citations_dropped:{repeated}')
        payload['evidence'] = kept
    return payload, notes


FIELD_PATH = re.compile(r'[a-z_]+(?:\[\d+\])?(?:\.[a-z_]+)?')


def contract_problem(payload) -> str:
    """Why normalize_payload rejects a payload, value-free: structure, known field paths and contract messages."""
    try:
        if not isinstance(payload, dict) or set(payload) != {'invoice', 'evidence'}:
            return 'top-level keys'
        if not isinstance(payload['evidence'], list):
            return 'evidence is not a list'
        evidence = {}
        for entry in payload['evidence']:
            if not isinstance(entry, dict) or set(entry) != {'field', 'page', 'raw_value'}:
                return 'evidence entry keys'
            name = entry['field'] if isinstance(entry['field'], str) and FIELD_PATH.fullmatch(entry['field']) \
                else 'unrecognized field'
            prior = evidence.get(entry['field'])
            if prior and (prior['page'], prior['raw_value']) != (entry['page'], entry['raw_value']):
                return 'conflicting evidence for ' + name
            evidence[entry['field']] = {'document_id': 'probe', 'page': entry['page'],
                                        'raw_value': entry['raw_value'], 'bbox': None}
        validate_extraction({'invoice': _absent(payload['invoice']), 'source_evidence': evidence})
    except ContractError as error:
        return str(error)
    except Exception:
        return 'unreadable structure'
    return 'unclassified'


def _jsonable(value):
    return json.loads(json.dumps(value, default=lambda item: f'<{type(item).__name__}>'))


def clean_response(response: dict) -> dict:
    """Converse response without raw HTTP headers; responses never echo the request images."""
    kept = {key: value for key, value in response.items() if key != 'ResponseMetadata'}
    meta = response.get('ResponseMetadata') or {}
    kept['ResponseMetadata'] = {key: meta[key] for key in ('RequestId', 'HTTPStatusCode', 'RetryAttempts')
                                if key in meta}
    return _jsonable(kept)


def returned_model(response: dict):
    # Converse does not echo the serving model; only a prompt router reports one.
    return ((response.get('trace') or {}).get('promptRouter') or {}).get('invokedModelId')


class BedrockClient:
    provider = 'bedrock'

    def __init__(self, config: BedrockConfig, ledger: BudgetLedger, runtime=None):
        if ledger.reservation < RESERVATION_MICRO_USD:
            raise LiveError('Bedrock needs a ledger that reserves at least US$0.05 per attempt.')
        self.config, self.ledger, self.model = config, ledger, config.model_id
        self.runtime = runtime if runtime is not None else self._runtime()

    def _runtime(self):
        import boto3
        session = boto3.session.Session(aws_access_key_id=self.config.access_key_id,
                                        aws_secret_access_key=self.config.secret_access_key,
                                        aws_session_token=self.config.session_token, region_name=REGION)
        # total_max_attempts, not max_attempts: botocore reads max_attempts as retries AFTER the first request.
        # One request only: a silent resend pushed documents past the 15 s brief target (18 s and 29 s on 14 Oct),
        # while a failure here goes to the logged OpenAI fallback. read_timeout stays 60 s because a valid
        # 5-page invoice needs 14 to 17 s.
        return session.client('bedrock-runtime', region_name=REGION, config=BotoConfig(
            read_timeout=60, connect_timeout=10, retries={'mode': 'standard', 'total_max_attempts': 1}))

    def preflight(self):
        """No network: Bedrock offers no free model probe here, so the cheap gate is the local ledger."""
        snapshot = self.ledger.snapshot()  # BudgetError when the ledger file is missing
        if any(state in BLOCKING_STATES for state in snapshot['states']):
            raise BudgetError('Bedrock ledger has an unreconciled attempt; inspect it before new calls.')
        if snapshot['remaining_calls'] < 1:
            raise BudgetError('Bedrock budget exhausted; no request was sent.')
        return {'provider': self.provider, 'model': self.model, 'region': REGION, 'ledger_ready': True,
                'remaining_calls': snapshot['remaining_calls'], 'network_calls': 0}

    def extract_pdf(self, pdf_bytes: bytes, case_id: str):
        return self.extract_document(pdf_bytes, 'application/pdf', case_id)

    def normalize(self, trace: dict, document_id: str) -> dict:
        return normalize_payload(trace['payload'], document_id)

    def _attempt(self, request, case_id):
        run_id = self.ledger.reserve(case_id)  # Durable before any network operation.
        started = time.perf_counter()
        try:
            response = self.runtime.converse(**request)
        except (ClientError, BotoCoreError) as error:
            # HTTP_ERROR, never UNCERTAIN, even for a read timeout whose request Bedrock may have billed. The
            # US$0.05 reservation is never refunded and already covers this attempt's worst case, including the
            # one resend botocore makes after a timeout (2 x worst_case_request_usd() < 0.05). An unknown outcome
            # therefore cannot overspend, and blocking every later call would turn one slow answer into an outage.
            self.ledger.finish(run_id, 'HTTP_ERROR')
            reason, code = failure_reason(error)
            raise BedrockError(reason, f'Bedrock call failed: {REASON_TEXT[reason]} ({code}). '
                                       'Attempt reserved; no further retry.') from None
        except Exception:
            # Not a botocore outcome at all: keep the conservative block until a person reviews the ledger.
            self.ledger.finish(run_id, 'UNCERTAIN')
            raise BedrockError('uncertain', 'Bedrock outcome unknown; further calls blocked until the ledger '
                                            'is reviewed.') from None
        duration = round((time.perf_counter() - started) * 1000)
        raw_usage = response.get('usage') if isinstance(response, dict) else None
        try:
            usage = billable_usage(raw_usage)
            retries = (response.get('ResponseMetadata') or {}).get('RetryAttempts') or 0
            if type(retries) is not int or retries < 0:
                raise LiveError('Unreadable retry count.')
            # A botocore resend may follow a billed timeout whose usage is lost: price it as a worst-case request.
            cost = usage_cost(usage) + retries * worst_case_request_usd()
            tier = (response.get('serviceTier') or {}).get('type')
            if tier not in (None, 'default') or cost > Decimal(self.ledger.reservation) / 1_000_000:
                raise LiveError('Unpriced tier or cost above the reservation.')
        except (LiveError, TypeError, ValueError, AttributeError):
            self.ledger.finish(run_id, 'COST_BREACH', _jsonable(raw_usage) if raw_usage is not None else None)
            raise BedrockError('budget', 'Bedrock billing unverified or above the reservation; '
                                         'further calls blocked.') from None
        self.ledger.finish(run_id, 'COMPLETED', usage, cost)
        return response, {'run_id': run_id, 'duration_ms': duration, 'usage': usage,
                          'cost_upper_estimate_usd': str(cost), 'stop_reason': response.get('stopReason'),
                          'retry_attempts': retries}

    def extract_document(self, data: bytes, media_type: str, case_id: str):
        """One document, at most two paid attempts: the second only when the first returns an invalid invoice."""
        started = time.perf_counter()
        pages = prepare_pages(data, media_type)  # rejects bad input before any reservation or network call
        request = build_request(self.model, pages)
        runs, rejected = [], []
        for attempt in (1, 2):
            response, run = self._attempt(request, case_id)
            runs.append(run)
            raw = tool_input(response)
            payload, notes = to_contract(raw) if raw is not None else (None, [])
            try:
                if payload is None:
                    raise LiveError('No single simpan_invoice call in the response.')
                normalize_payload(payload, 'validation-probe')
            except LiveError:
                run['outcome'] = 'INVALID_OUTPUT'
                run['problem'] = 'no single simpan_invoice call' if payload is None else contract_problem(payload)
                rejected.append(clean_response(response))
                if attempt == 1:
                    continue
                raise BedrockError('invalid_output', f'Invalid structured invoice response ({run["problem"]}); '
                                                     'second attempt also invalid, no further retry.',
                                   runs, rejected) from None
            run['outcome'] = 'ACCEPTED'
            return {'provider': self.provider, 'run_id': run['run_id'], 'attempts': len(runs), 'attempt_runs': runs,
                    'duration_ms': round((time.perf_counter() - started) * 1000),
                    'usage': {key: sum(r['usage'][key] for r in runs) for key in ('input_tokens', 'output_tokens')},
                    'cost_upper_estimate_usd': str(sum((Decimal(r['cost_upper_estimate_usd']) for r in runs),
                                                       Decimal(0))),
                    'billed_cost_usd': None, 'price_verified_on': PRICE_VERIFIED, 'prompt_version': PROMPT_VERSION,
                    'prompt_sha256': hashlib.sha256(PROMPT.encode()).hexdigest(),
                    'request_profile': request_profile(), 'requested_model': self.model,
                    'returned_model': returned_model(response), 'region': REGION,
                    'stop_reason': response.get('stopReason'), 'adaptations': notes,
                    'pages': [{'page': n, 'format': p['format'], 'width': p['size'][0], 'height': p['size'][1],
                               'image_bytes': len(p['bytes']), 'text_hint': p['hint'] is not None}
                              for n, p in enumerate(pages, 1)],
                    'payload': payload, 'response': clean_response(response), 'rejected_responses': rejected}


def client_from_env(runtime=None):
    """Integration point for app/service.py: config from the local .env, production Bedrock ledger."""
    config = BedrockConfig.load()
    return BedrockClient(config, BudgetLedger(LEDGER_PATH, config.stop_usd, RESERVATION_MICRO_USD), runtime)


def _env_stop_usd():
    path = ROOT / '.env'
    if not path.is_file():
        return DEFAULT_STOP_USD
    try:
        return parse_stop_usd(read_dotenv(path).get('AMIGA_BEDROCK_STOP_USD'))
    except (OSError, UnicodeError):
        raise LiveError('Local .env unreadable; values hidden.') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description='Bedrock spend ledger for AMIGA. It is never reset.')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--init-ledger', action='store_true', help='provision the ledger once; refuses if it exists')
    action.add_argument('--snapshot', action='store_true', help='print reservations and estimated usage')
    args = parser.parse_args(argv)
    try:
        ledger = BudgetLedger(LEDGER_PATH, _env_stop_usd(), RESERVATION_MICRO_USD)
        if args.init_ledger:
            try:
                ledger.initialize()
            except FileExistsError:
                print('Bedrock ledger already exists; it is never reset.', file=sys.stderr)
                return 1
            print('Provisioned ' + LEDGER_PATH.relative_to(ROOT).as_posix())
        print(json.dumps(ledger.snapshot(), indent=2))
    except (LiveError, BudgetError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
