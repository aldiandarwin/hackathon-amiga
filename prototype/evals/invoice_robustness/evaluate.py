"""Offline-only invoice evaluation. Reads saved outputs; never invokes OCR APIs."""

import argparse
import ast
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import re
import socket
import sqlite3
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'prototype'))
from amiga_ocr.contracts import Context, ContractError, OCRDocument, OCRPage, Rules, validate_extraction
from amiga_ocr.validation import field_values, normalized_text, validate_invoice

DATA = ROOT / 'prototype/dataset/robustness-v1'
OUTPUT = ROOT / 'output/evaluation/robustness-v1'
GRADER_VERSION = 'invoice-deterministic.v1'
DEV_SPLITS = ('regression', 'targeted')


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def canonical(cases):
    return '\n'.join(json.dumps(c, ensure_ascii=False, sort_keys=True, separators=(',', ':')) for c in cases).encode()


def load_cases():
    cases = [json.loads(line) for line in (DATA / 'cases.jsonl').read_text(encoding='utf-8').splitlines()]
    manifest = json.loads((DATA / 'manifest.json').read_text(encoding='utf-8'))
    if sha256(canonical(cases)).hexdigest() != manifest['dataset_sha256'] or digest(DATA / 'cases.jsonl') != manifest['cases_jsonl_sha256']:
        raise ValueError('Frozen dataset changed; create and review a new version.')
    if len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate dataset case IDs.')
    for case in cases:
        path = (ROOT / case['input']['pdf']).resolve()
        if not path.is_relative_to(ROOT / 'output/pdf') or digest(path) != case['input']['pdf_sha256']:
            raise ValueError('PDF path or hash changed: ' + case['case_id'])
    return cases, manifest


def budget_snapshot():
    path = ROOT / 'prototype/.local/spend.sqlite3'
    if not path.is_file():
        return {'available': False}
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
        rows = conn.execute('SELECT state,reserved,cost_upper_usd FROM attempts ORDER BY created').fetchall()
    return {'available': True, 'attempt_count': len(rows), 'states': [row[0] for row in rows],
            'reserved_authorization_usd': str(Decimal(sum(row[1] for row in rows)) / 1000000),
            'usage_cost_upper_estimate_usd': str(sum((Decimal(row[2]) for row in rows if row[2] is not None), Decimal(0)))}


def source_metadata():
    files = list((ROOT / 'prototype/amiga_ocr').glob('*.py')) + [Path(__file__), Path(__file__).with_name('build_dataset.py')]
    hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)}
    tree = ast.parse((ROOT / 'prototype/amiga_ocr/openai_live.py').read_text(encoding='utf-8'))
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('MODEL', 'PROMPT_VERSION', 'PROMPT'):
            constants[node.targets[0].id] = ast.literal_eval(node.value)
    return {'code_sha256': sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(), 'code_files': hashes,
            'reference_model_not_executed': constants['MODEL'], 'reference_prompt_version': constants['PROMPT_VERSION'],
            'reference_prompt_sha256': sha256(constants['PROMPT'].encode()).hexdigest(),
            'rules_version': Rules().version, 'rules_tolerance': str(Rules().tolerance), 'grader_version': GRADER_VERSION,
            'python': sys.version.split()[0], 'libraries': {name: importlib.metadata.version(name) for name in ('reportlab', 'pypdf', 'PyMuPDF')}}


def extraction_for(case):
    expected = case['expected_behavior']
    return deepcopy({'invoice': expected['invoice'], 'source_evidence': expected['source_evidence']})


def compare_fields(expected, actual):
    wanted, got = dict(field_values(expected)), dict(field_values(actual))
    fields, errors = sorted(set(wanted) | set(got)), []
    for field in fields:
        left, right = wanted.get(field), got.get(field)
        numeric = field.startswith('stated_') or field.endswith(('.quantity', '.unit_price', '.stated_line_total'))
        equal = Decimal(left) == Decimal(right) if numeric and left is not None and right is not None else left == right
        if field not in wanted or field not in got or not equal:
            errors.append(field)
    if len(expected['line_items']) != len(actual['line_items']):
        errors.append('line_items.length')
    return {'passed': not errors, 'checked_scalar_fields': len(fields), 'mismatched_fields': errors,
            'expected_rows': len(expected['line_items']), 'actual_rows': len(actual['line_items'])}


def compare_evidence(case, extraction):
    expected = case['expected_behavior']['source_evidence']
    actual = extraction['source_evidence']
    errors = []
    for field, entry in expected.items():
        got = actual.get(field)
        if entry is None:
            if got is not None:
                errors.append({'field': field, 'reason': 'EVIDENCE_FOR_ABSENT_VALUE'})
            continue
        if got is None:
            errors.append({'field': field, 'reason': 'MISSING_EVIDENCE'})
            continue
        # Repeated headers can legitimately be cited on more than one original page.
        # Match the source quote independently, rather than forcing the author's first occurrence.
        quote = normalized_text(entry['raw_value'])
        allowed_pages = {i + 1 for i, text in enumerate(case['expected_behavior']['annotated_pages'])
                         if re.search(rf'(?<!\w){re.escape(quote)}(?!\w)', normalized_text(text))}
        if got['document_id'] != case['input']['document_id'] or got['page'] not in allowed_pages:
            errors.append({'field': field, 'reason': 'WRONG_SOURCE_PAGE_OR_DOCUMENT'})
        if normalized_text(got['raw_value']) != normalized_text(entry['raw_value']):
            errors.append({'field': field, 'reason': 'SOURCE_QUOTE_DIFFERENT_FROM_ANNOTATION'})
    for field in set(actual) - set(expected):
        errors.append({'field': field, 'reason': 'UNEXPECTED_EVIDENCE_FIELD'})
    return {'passed': not errors, 'errors': errors, 'basis': 'AUTHOR_ANNOTATION_WITH_VISUAL_QA',
            'limitation': 'Repeated source values can appear on several pages; no bounding-box or row-association proof. Alternative quotes need reviewed annotation.'}


def grade_case(case, extraction):
    start = time.perf_counter()
    result = {'case_id': case['case_id'], 'split': case['split'], 'severity': case['severity'],
              'expected_status': case['expected_behavior']['status'], 'input_sha256': case['input']['pdf_sha256']}
    try:
        valid = validate_extraction(extraction)
    except (ContractError, TypeError, ValueError, KeyError) as error:
        return result | {'passed': False, 'execution': 'INVALID_OUTPUT_CONTRACT', 'error': str(error),
                         'layer': 'OUTPUT_SCHEMA', 'grading_duration_ms': round((time.perf_counter() - start) * 1000, 3)}
    fields = compare_fields(case['expected_behavior']['invoice'], valid['invoice'])
    evidence = compare_evidence(case, valid)
    # This tests the unchanged validator against the author's transcript, not an OCR engine.
    pages = case['expected_behavior']['annotated_pages']
    document = OCRDocument(case['input']['document_id'], 'author-annotation', 'none',
        tuple(OCRPage(i + 1, text) for i, text in enumerate(pages)), case['input']['invoice_page_count'], True, {})
    validation = validate_invoice(valid, document, Context(**case['input']['context']), Rules())
    blocking = sorted({item['code'] + ':' + item['status'] for item in validation['checks'] if item['blocking'] and item['status'] != 'PASSED'})
    codes = {item['code'] + ':' + item['status'] for item in validation['checks']}
    status = 'EXCEPTION' if blocking else 'READY_FOR_REVIEW'
    workflow_pass = (status == case['expected_behavior']['status']
        and blocking == sorted(case['expected_behavior']['blocking_checks'])
        and set(case['expected_behavior']['required_checks']) <= codes)
    return result | {'execution': 'COMPLETED', 'passed': fields['passed'] and evidence['passed'] and workflow_pass,
        'fields': fields, 'evidence': evidence, 'validation_passed': workflow_pass,
        'actual_status': status, 'blocking_checks': blocking, 'validation': validation,
        'grading_duration_ms': round((time.perf_counter() - start) * 1000, 3),
        'layer': 'NONE' if fields['passed'] and evidence['passed'] and workflow_pass else 'SEE_FIELD_EVIDENCE_AND_VALIDATION_RESULTS'}


def validate_saved_records(cases, records, allow_holdout=False):
    selected = {c['case_id']: c for c in cases if allow_holdout or c['split'] in DEV_SPLITS}
    indexed = {}
    for record in records:
        identifier = record.get('case_id')
        if identifier not in selected:
            raise ValueError('Unknown or locked holdout case ID: ' + str(identifier))
        if identifier in indexed:
            raise ValueError('Duplicate saved output case ID: ' + identifier)
        if record.get('input_sha256') != selected[identifier]['input']['pdf_sha256']:
            raise ValueError('Saved output PDF hash does not match dataset: ' + identifier)
        provenance = record.get('provenance', {})
        if not all(isinstance(provenance.get(key), str) and provenance[key].strip() for key in ('model', 'prompt_version')):
            raise ValueError('Saved output requires model and prompt version: ' + identifier)
        if not re.fullmatch('[a-f0-9]{64}', provenance.get('prompt_sha256', '')) or not isinstance(provenance.get('parameters'), dict):
            raise ValueError('Saved output requires prompt hash and parameters: ' + identifier)
        if record.get('execution') not in ('COMPLETED', 'ERROR'):
            raise ValueError('Saved output execution must be COMPLETED or ERROR.')
        indexed[identifier] = record
    return selected, indexed


def grade_saved(cases, records, allow_holdout=False):
    selected, indexed = validate_saved_records(cases, records, allow_holdout)
    results = []
    for identifier, case in selected.items():
        record = indexed.get(identifier)
        if record is None or record['execution'] != 'COMPLETED':
            results.append({'case_id': identifier, 'split': case['split'], 'severity': case['severity'], 'passed': False,
                            'execution': 'MISSING_OUTPUT' if record is None else 'PROVIDER_EXECUTION_ERROR'})
        else:
            result = grade_case(case, record.get('extraction'))
            result['reported_provenance_unverified'] = record['provenance']
            result['ocr_latency_ms'] = record.get('duration_ms')
            result['reported_cost_usd'] = record.get('cost_usd')
            # Raw OCR transcripts are optional; absence cannot identify an OCR-vs-mapping cause.
            result['root_cause_status'] = 'UNDETERMINED_WITHOUT_REVIEWED_INTERMEDIATE_TRACE'
            results.append(result)
    return results


def mutation_controls(cases):
    lookup = {c['case_id'].split('.')[2]: c for c in cases if c['split'] in DEV_SPLITS}
    controls = []

    def run(name, short, change):
        case = lookup[short]
        extraction = extraction_for(case)
        change(extraction)
        result = grade_case(case, extraction)
        controls.append({'control_id': name, 'case_id': case['case_id'], 'mode': 'MUTATION_CONTROL_NOT_MODEL_OUTPUT',
                         'expected_rejection': True, 'rejected': not result['passed'], 'details': result})

    run('leading_zero_lost', 'r02', lambda p: p['invoice']['payment'].__setitem__('account_number', '1230045'))
    run('line_item_omitted', 'r01', lambda p: p['invoice']['line_items'].pop())
    run('invented_missing_account', 't05', lambda p: p['invoice']['payment'].__setitem__('account_number', '009900000099'))
    run('total_silently_repaired', 't06', lambda p: p['invoice'].__setitem__('stated_total', p['invoice']['stated_subtotal']))
    run('wrong_source_page', 't01', lambda p: p['source_evidence']['line_items[19].description'].__setitem__('page', 1))
    run('fabricated_quote', 'r01', lambda p: p['source_evidence']['payment.account_number'].__setitem__('raw_value', '999999999'))
    run('critical_evidence_omitted', 'r01', lambda p: p['source_evidence'].pop('payment.account_number'))
    run('numeric_float_instead_of_string', 'r01', lambda p: p['invoice'].__setitem__('stated_total', 123.0))
    run('missing_required_schema_key', 'r01', lambda p: p['invoice'].pop('currency'))
    run('model_invented_vendor_id', 'r01', lambda p: p['invoice'].__setitem__('vendor_id', 'untrusted_vendor'))
    def swap(p):
        items = p['invoice']['line_items']
        items[0], items[1] = items[1], items[0]
        for i, item in enumerate(items):
            item['line_number'] = i + 1
    run('rows_reordered', 't01', swap)
    def extra(p):
        item = deepcopy(p['invoice']['line_items'][0])
        item['line_number'] = len(p['invoice']['line_items']) + 1
        p['invoice']['line_items'].append(item)
    run('invented_extra_row', 'r01', extra)
    return controls


def write_report(report, destination):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    rows = []
    for result in report['results']:
        rows.append(f"| {result['case_id']} | {result['split']} | {'PASS' if result['passed'] else 'FAIL'} | {result['execution']} | {result.get('actual_status', '-')} |")
    text = '# Invoice robustness — hasil evaluasi lokal\n\n'
    text += f"Mode: **{report['mode']}**. Verdict kualitas OCR: **INCONCLUSIVE**.\n\n"
    text += 'Baseline oracle memasukkan jawaban sintetis ideal ke validator yang belum diubah. Hasil ini memeriksa kontrak dan aturan lokal; tidak mengukur kemampuan model membaca PDF.\n\n' if report['mode'] == 'OFFLINE_ORACLE_VALIDATION' else 'Output provider tersimpan dinilai secara deterministik. Metadata provider adalah laporan dari file input; tidak diverifikasi ke layanan. Jawaban sintetis tetap perlu review Finance.\n\n'
    text += f"Kasus lulus: {sum(r['passed'] for r in report['results'])}/{len(report['results'])}. Holdout yang tidak dijalankan: {report['holdout_not_run']}.\n\n"
    text += '| Kasus | Split | Hasil lokal | Eksekusi | Status validasi |\n|---|---|---|---|---|\n' + '\n'.join(rows)
    controls = report.get('mutation_controls', [])
    if controls:
        text += f"\n\nKalibrasi grader: {sum(c['rejected'] for c in controls)}/{len(controls)} kontrol cacat sengaja ditolak. Ini bukan output model atau perbaikan kandidat.\n"
    text += '\nTidak ada candidate model, panggilan OCR live, klaim SLA, atau klaim peningkatan akurasi pada run ini. Pemeriksaan scan menggunakan anotasi authoring; aplikasi tetap membutuhkan review visual terhadap sumber raster.\n'
    text += '\nHash dataset: `' + report['dataset_sha256'] + '`. Metadata, perbedaan field, evidence, kode aturan, timing grader, dan snapshot ledger ada di `results.json`. Waktu grader bukan latency OCR.\n'
    (destination / 'REPORT.md').write_text(text, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('baseline', 'grade'))
    parser.add_argument('--predictions', type=Path)
    parser.add_argument('--include-holdout', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(OUTPUT):
        parser.error('Output must remain inside output/evaluation/robustness-v1.')
    if args.mode == 'baseline' and (args.include_holdout or args.predictions):
        parser.error('Baseline always keeps holdout unused; predictions belong to grade mode.')
    if args.mode == 'grade' and args.predictions is None:
        parser.error('grade requires --predictions. This runner never calls an API.')
    with patch.object(socket, 'socket', side_effect=RuntimeError('Network disabled in offline evaluation')):
        cases, manifest = load_cases()
        before = budget_snapshot()
        if args.mode == 'baseline':
            results = [grade_case(c, extraction_for(c)) for c in cases if c['split'] in DEV_SPLITS]
            controls = mutation_controls(cases)
        else:
            records = [json.loads(line) for line in args.predictions.read_text(encoding='utf-8').splitlines() if line.strip()]
            results, controls = grade_saved(cases, records, args.include_holdout), []
        after = budget_snapshot()
        if before != after:
            raise RuntimeError('Ledger changed during evaluation; investigate concurrent activity.')
        report = {'verified_at_utc': datetime.now(timezone.utc).isoformat(),
            'mode': 'OFFLINE_ORACLE_VALIDATION' if args.mode == 'baseline' else 'SAVED_PROVIDER_OUTPUTS',
            'ocr_quality_verdict': 'INCONCLUSIVE', 'dataset_sha256': manifest['dataset_sha256'],
            'metadata': source_metadata(), 'execution_model': None if args.mode == 'baseline' else 'SEE_REPORTED_RECORD_PROVENANCE',
            'results': results, 'mutation_controls': controls,
            'split_counts': dict(Counter(r['split'] for r in results)),
            'holdout_not_run': sum(c['split'] == 'holdout' for c in cases) if not args.include_holdout else 0,
            'candidate_comparison': 'NOT_RUN', 'live_ocr_calls': 0,
            'budget_before': before, 'budget_after': after, 'budget_unchanged': True}
        write_report(report, args.output)
    print(json.dumps({'mode': report['mode'], 'passed': sum(r['passed'] for r in results), 'total': len(results),
                      'mutation_controls_rejected': sum(c['rejected'] for c in controls), 'holdout_not_run': report['holdout_not_run'],
                      'budget_unchanged': True, 'ocr_quality': 'INCONCLUSIVE'}, indent=2))
    return 0 if all(r['passed'] for r in results) and all(c['rejected'] for c in controls) else 1


if __name__ == '__main__':
    raise SystemExit(main())
