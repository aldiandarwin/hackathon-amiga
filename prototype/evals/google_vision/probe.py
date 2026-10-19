"""Bounded Google Vision OCR experiment. Default is a local plan, never an API call."""

import argparse
import base64
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import time

import httpx
import pymupdf

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'output/evaluation/google-vision'
PRIVATE = ROOT / '.appdata/google-vision'
ENDPOINT = 'https://vision.googleapis.com/v1/images:annotate'
SELECTED = ('r03', 't01', 't03')
MAX_UNITS_PER_RUN = 7
FEATURE = 'DOCUMENT_TEXT_DETECTION'


def load_key():
    # The user stored the Google key as lowercase `key`; parse as data, not shell code.
    fields = {}
    for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines():
        name, sep, value = line.partition('=')
        if sep and name.strip() in ('GOOGLE_VISION_API_KEY', 'key'):
            fields[name.strip()] = value.strip().strip('"').strip("'")
    key = fields.get('GOOGLE_VISION_API_KEY') or fields.get('key')
    if not key or not key.startswith('AIza') or any(c.isspace() for c in key):
        raise ValueError('Google API key missing or invalid; value hidden.')
    return key


def plan(selected=SELECTED):
    manifest = ROOT / 'prototype/dataset/robustness-v1/inputs-only.jsonl'
    inputs = [json.loads(line) for line in manifest.read_text(encoding='utf-8').splitlines()]
    cases = []
    for short in selected:
        matches = [item for item in inputs if item['case_id'] == f'amiga.robust.{short}.v1']
        if len(matches) != 1:
            raise ValueError('Unknown or duplicate selected case.')
        case = matches[0]
        path = (ROOT / case['pdf']).resolve()
        if not path.is_relative_to(ROOT / 'output/pdf/robustness-v1') or sha256(path.read_bytes()).hexdigest() != case['pdf_sha256']:
            raise ValueError('Input PDF changed; refusing to send it.')
        with pymupdf.open(path) as document:
            if document.page_count != case['invoice_page_count'] or not 1 <= document.page_count <= 5:
                raise ValueError('Input page count changed or exceeds demo bounds.')
        cases.append(case)
    units = sum(case['invoice_page_count'] for case in cases)
    if len(set(selected)) != len(selected) or not 1 <= units <= MAX_UNITS_PER_RUN:
        raise ValueError('Duplicate cases or run exceeds seven image/feature units.')
    return {'provider': 'google_cloud_vision', 'feature': FEATURE, 'units': units, 'cases': cases,
            'render_dpi': 150, 'mode': 'LOCAL_PLAN_NO_API', 'free_tier_units_per_month': 1000,
            'remaining_account_free_units': None, 'billed_cost_usd': None,
            'conditional_free_tier_cost_usd': '0', 'first_paid_tier_cost_if_no_free_units_usd': f'{units * 0.0015:.4f}',
            'billing_prerequisite': 'Google project billing must be active, even for free-tier OCR.',
            'structured_invoice_extraction': 'NOT_PERFORMED_BY_VISION_OCR'}


def request_document(client, key, images):
    if not 1 <= len(images) <= 5:
        raise ValueError('One to five page images allowed.')
    payload = {'requests': [{'image': {'content': base64.b64encode(image).decode('ascii')},
                            'features': [{'type': FEATURE}]} for image in images]}
    # No labels, expected invoice, master data or author transcript enters this payload.
    started = time.perf_counter()
    try:
        response = client.post(ENDPOINT, headers={'X-Goog-Api-Key': key}, json=payload)
        raw = response.json()
    except Exception as error:
        return {'execution': 'TRANSPORT_OR_JSON_ERROR', 'error_type': type(error).__name__,
                'duration_ms': round((time.perf_counter() - started) * 1000), 'retry_performed': False}, None
    error = raw.get('error') if isinstance(raw, dict) else None
    responses = raw.get('responses') if isinstance(raw, dict) else None
    if error is None and isinstance(responses, list):
        error = next((item.get('error') for item in responses if isinstance(item, dict) and item.get('error')), None)
    reasons = [item['reason'] for item in error.get('details', []) if isinstance(item, dict) and 'reason' in item] if isinstance(error, dict) else []
    execution = 'API_ERROR' if error or response.status_code != 200 else 'COMPLETED'
    if execution == 'COMPLETED' and (not isinstance(responses, list) or len(responses) != len(images)
        or any(not isinstance(item, dict) or not item.get('fullTextAnnotation', {}).get('text', '').strip() for item in responses)):
        execution = 'PARTIAL_OR_EMPTY_OCR'
    result = {'execution': execution, 'http_status': response.status_code,
        'google_status': error.get('status') if isinstance(error, dict) else None,
        'error_reasons': reasons, 'duration_ms': round((time.perf_counter() - started) * 1000),
        'units_submitted': len(images), 'retry_performed': False}
    return result, raw


def quote_coverage(case, texts):
    # Answers are used ONLY after OCR to grade text availability, never to derive output fields.
    dataset = ROOT / 'prototype/dataset/robustness-v1/cases.jsonl'
    expected = next(json.loads(line)['expected_behavior'] for line in dataset.read_text(encoding='utf-8').splitlines()
                    if json.loads(line)['case_id'] == case['case_id'])
    missing, total = [], 0
    for field, entry in expected['source_evidence'].items():
        if entry is None:
            continue
        total += 1
        page = entry['page'] - 1
        text = ' '.join(texts[page].split()) if page < len(texts) else ''
        quote = ' '.join(entry['raw_value'].split())
        if not re.search(rf'(?<!\w){re.escape(quote)}(?!\w)', text):
            missing.append(field)
    return {'metric': 'SOURCE_QUOTE_COVERAGE_NO_STRUCTURED_EXTRACTION', 'found': total - len(missing),
            'total': total, 'missing_source_fields': missing,
            'limitation': 'Quote presence does not prove field mapping, table association, row order, or invoice JSON accuracy.'}


def run(selected, output):
    if not output.resolve().is_relative_to(OUTPUT):
        raise ValueError('Result path must stay inside output/evaluation/google-vision.')
    checked, key = plan(selected), load_key()
    output.mkdir(parents=True, exist_ok=False)
    private = PRIVATE / output.name
    private.mkdir(parents=True, exist_ok=False)
    results = []
    with httpx.Client(timeout=45, follow_redirects=False, trust_env=False) as client:
        for case in checked['cases']:
            with pymupdf.open(ROOT / case['pdf']) as document:
                images = [page.get_pixmap(dpi=150, alpha=False).tobytes('png') for page in document]
            result, raw = request_document(client, key, images)
            result.update(case_id=case['case_id'], pdf_sha256=case['pdf_sha256'])
            if raw is not None:
                # Never retain headers or credentials; redact any server reflection of the key.
                (private / (case['case_id'] + '.json')).write_text(
                    json.dumps(raw, ensure_ascii=False, indent=2).replace(key, '[REDACTED]'), encoding='utf-8')
            if result['execution'] == 'COMPLETED':
                texts = [item['fullTextAnnotation']['text'] for item in raw['responses']]
                result['quote_coverage'] = quote_coverage(case, texts)
                result['pages_received'] = len(texts)
                (output / (case['case_id'] + '.txt')).write_text('\n\n'.join(f'PAGE {i + 1}\n{text}' for i, text in enumerate(texts)), encoding='utf-8')
            results.append(result)
            if result['execution'] != 'COMPLETED':
                break  # Never retry or spend units on the other samples after an error.
    report = checked | {'mode': 'LIVE_GOOGLE_VISION', 'verified_at_utc': datetime.now(timezone.utc).isoformat(),
        'results': results, 'units_submitted': sum(r.get('units_submitted', 0) for r in results),
        'ocr_quality_verdict': 'INCONCLUSIVE', 'invoice_extraction_verdict': 'NOT_TESTED',
        'code_sha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'retry_performed': False}
    (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Explicitly call Google; needs active billing and free quota.')
    parser.add_argument('--cases', nargs='+', choices=SELECTED, default=list(SELECTED))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.run:
        if args.output is None:
            parser.error('--run requires a fresh --output directory.')
        report = run(tuple(args.cases), args.output)
    else:
        report = plan(tuple(args.cases))
        try:
            load_key()
            report['key_configured'] = True
        except ValueError:
            report['key_configured'] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not args.run or all(r['execution'] == 'COMPLETED' for r in report['results']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
