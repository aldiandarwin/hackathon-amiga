"""Small explicit live run, defaulting to a free local budget-status read."""

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys

from amiga_ocr.contracts import OCRDocument, OCRPage, Rules
from amiga_ocr.fixtures import scenario
from amiga_ocr.live_budget import BudgetError, BudgetLedger
from amiga_ocr.openai_live import Config, LiveError, OpenAIClient, ROOT, normalize_response
from amiga_ocr.validation import field_values, validate_invoice

LEDGER = ROOT / 'prototype' / '.local' / 'spend.sqlite3'
DATASET = ROOT / 'prototype' / 'dataset' / 'cases.jsonl'


def field_grade(expected, actual):
    """Predeclared exact strings/nulls and Decimal equality; never an AI grader."""
    wanted, obtained = dict(field_values(expected)), dict(field_values(actual))
    mismatches = []
    if len(expected['line_items']) != len(actual['line_items']):
        mismatches.append('line_items.length')
    for path in sorted(set(wanted) | set(obtained)):
        left, right = wanted.get(path), obtained.get(path)
        numeric = path.startswith('stated_') or path.endswith(('.quantity', '.unit_price', '.stated_line_total'))
        matches = Decimal(left) == Decimal(right) if numeric and left is not None and right is not None else left == right
        if not matches:
            mismatches.append(path)
    return {'passed': not mismatches, 'checked_fields': len(wanted), 'mismatched_fields': mismatches}


def run_case(case, client):
    from pypdf import PdfReader, PdfWriter
    source = (ROOT / case['input']['pdf']).resolve()
    if not source.is_relative_to(ROOT) or hashlib.sha256(source.read_bytes()).hexdigest() != case['input']['pdf_sha256']:
        raise LiveError('Fixture path or hash changed; no API call sent.')
    page = PdfReader(source).pages[case['input']['pack_page'] - 1]
    writer, buffer = PdfWriter(), BytesIO()
    writer.add_page(page)
    writer.write(buffer)
    pdf_bytes = buffer.getvalue()
    # The model receives ONLY the PDF, never golden JSON or trusted bank context.
    trace = client.extract_pdf(pdf_bytes, case['case_id'])
    output = ROOT / 'prototype' / 'output' / 'live' / trace['run_id']
    output.mkdir(parents=True, exist_ok=False)
    (output / 'trace.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding='utf-8')
    result = {'case_id': case['case_id'], 'run_id': trace['run_id'],
              'mode': 'LIVE_OPENAI_SYNTHETIC_PDF', 'dataset_sha256': hashlib.sha256(DATASET.read_bytes()).hexdigest(),
              'input_sha256': hashlib.sha256(pdf_bytes).hexdigest(),
              'code_sha256': hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'prototype'/'amiga_ocr').glob('*.py')))
                                           + Path(__file__).read_bytes()).hexdigest(),
              'duration_ms': trace['duration_ms'], 'usage': trace['usage'],
              'cost_upper_estimate_usd': trace['cost_upper_estimate_usd'], 'billed_cost_usd': None,
              'prompt_version': trace['prompt_version'], 'model': trace['returned_model'],
              'review': {'required': True, 'can_approve': False, 'reason': 'EXPERIMENT_ONLY_NO_AUTH_OR_APPROVAL_API'}}
    try:
        extraction = normalize_response(trace['response'], case['input']['document_id'])
        grade = field_grade(case['expected_behavior']['invoice'], extraction['invoice'])
        text = page.extract_text() or ''
        document = OCRDocument(case['input']['document_id'], 'openai', trace['returned_model'],
                               (OCRPage(1, text, bool(text)),), 1, bool(text), {})
        # Evidence is independently checked against embedded PDF text, not model-generated transcription.
        validation = validate_invoice(deepcopy(extraction), document,
                                      scenario(case['metadata']['scenario']).context, Rules())
        status = 'EXCEPTION' if any(c['blocking'] and c['status'] != 'PASSED' for c in validation['checks']) else 'READY_FOR_REVIEW'
        codes = {c['code'] for c in validation['checks']}
        workflow_pass = status == case['expected_behavior']['status'] and set(case['expected_behavior']['required_check_codes']) <= codes
        result.update({'invoice': extraction['invoice'], 'source_evidence': extraction['source_evidence'],
                       'validation': validation, 'request_status': status, 'field_grade': grade,
                       'workflow_pass': workflow_pass, 'passed': grade['passed'] and workflow_pass,
                       'execution': 'COMPLETED', 'source_check': 'INDEPENDENT_EMBEDDED_PDF_TEXT'})
    except LiveError as error:
        result.update({'execution': 'INVALID_MODEL_OUTPUT', 'passed': False, 'error': str(error)})
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true', help='Check key/model availability; no generation.')
    parser.add_argument('--run', choices=('normal', 'missing_bank', 'wrong_total', 'all'))
    args = parser.parse_args()
    config = Config.load()
    ledger = BudgetLedger(LEDGER, config.stop_usd)
    client = OpenAIClient(config, ledger)
    try:
        if args.preflight or args.run:
            print(json.dumps(client.preflight()))
        if args.run:
            cases = [json.loads(line) for line in DATASET.read_text(encoding='utf-8').splitlines()]
            for case in cases:
                if args.run != 'all' and case['metadata']['scenario'] != args.run:
                    continue
                result = run_case(case, client)
                print(json.dumps({k: result[k] for k in ('case_id', 'run_id', 'execution', 'passed', 'duration_ms', 'cost_upper_estimate_usd')}, ensure_ascii=False), flush=True)
                if not result['passed']:
                    print('Stopped after first failure for inspection; no automatic rerun.')
                    break
        print(json.dumps(ledger.snapshot(), indent=2))
    except (BudgetError, LiveError) as error:
        print(json.dumps({'error': str(error), 'automatic_retry': False}), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
