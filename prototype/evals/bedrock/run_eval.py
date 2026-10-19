"""Paid Bedrock evaluation on synthetic invoices only; real invoices only through --real-case.

Set A: the 10 development cases of prototype/dataset/robustness-v1, graded by the unchanged deterministic grader.
Holdout cases are never sent (the grader's integrity check only hashes their files). Set B: every existing file
listed in output/pdf/demo-final/manifest.json (PDF, JPEG or PNG), compared field by field with expected_invoice.

Every call goes through BedrockClient and the eval ledger prototype/.local/spend-bedrock-eval.sqlite3 (US$0.05
reserved per attempt, never refunded; cap 1.00 by default, cumulative across runs). The run refuses to start when the
ledger cannot cover every planned document, and halts after two consecutive network failures so a dead connection
cannot drain the reservations. All reported numbers are recomputed offline from the saved traces (analyze_run), so
runs made with different prompts are measured by the same code.

From the hackthon root:
    .venv\\Scripts\\python.exe -B prototype/evals/bedrock/run_eval.py
    .venv\\Scripts\\python.exe -B prototype/evals/bedrock/run_eval.py --output output/app-stage6/bedrock-eval/run-2 \\
        --cap-usd 1.85 --b-files inv-demo-002.pdf,inv-demo-006.jpg
    .venv\\Scripts\\python.exe -B prototype/evals/bedrock/run_eval.py --compare output/app-stage6/bedrock-eval \\
        output/app-stage6/bedrock-eval/run-2                      (offline, writes the side-by-side REPORT.md)
    .venv\\Scripts\\python.exe -B prototype/evals/bedrock/run_eval.py --real-case <folder> [--cap-usd 1.50]

--real-case reads <folder>/manifest.json (same shape as demo-final, paths relative to the folder) or, without one,
every PDF/JPEG/PNG in the folder. Details go ONLY to .appdata/real-case/bedrock-eval/<UTC time>/; the console gets
aggregate numbers only, and ledger case IDs carry no file names.
"""

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import socket
import ssl
import statistics
import sys
from unittest.mock import patch

import pymupdf

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'prototype'))
from amiga_ocr.bedrock_live import (PRICE_INPUT_PER_M, PRICE_OUTPUT_PER_M, PRICE_VERIFIED, REGION,  # noqa: E402
                                    RESERVATION_MICRO_USD, BedrockClient, BedrockConfig, BedrockError,
                                    request_profile, usage_cost)
from amiga_ocr.contracts import METADATA_FIELDS  # noqa: E402
from amiga_ocr.live_budget import BudgetError, BudgetLedger  # noqa: E402
from amiga_ocr.openai_live import MEDIA_TYPES, PROMPT, PROMPT_VERSION, LiveError, normalize_payload  # noqa: E402
from amiga_ocr.validation import field_values, normalized_text  # noqa: E402

EVAL_LEDGER = ROOT / 'prototype' / '.local' / 'spend-bedrock-eval.sqlite3'
EVAL_CAP_USD = Decimal('1.00')
MAX_CAP_USD = Decimal('2.00')
OUTPUT_ROOT = ROOT / 'output' / 'app-stage6'
# Stage 8 re-measures after the 14 Oct retry fix; earlier stages stay untouched evidence.
OUTPUT_ROOTS = (OUTPUT_ROOT, ROOT / 'output' / 'app-stage8')
DEFAULT_OUTPUT = OUTPUT_ROOT / 'bedrock-eval'
CASES = ROOT / 'prototype' / 'dataset' / 'robustness-v1' / 'cases.jsonl'
DEMO_MANIFEST = ROOT / 'output' / 'pdf' / 'demo-final' / 'manifest.json'
REAL_CASE_OUTPUT = ROOT / '.appdata' / 'real-case' / 'bedrock-eval'
ENDPOINT = f'bedrock-runtime.{REGION}.amazonaws.com'
NETWORK_REASONS = ('network', 'timeout')
HALTING_REASONS = ('budget', 'uncertain', 'access_denied')
AMOUNTS = {'stated_subtotal', 'stated_discount_total', 'stated_tax_total', 'stated_total', 'quantity', 'unit_price',
           'stated_line_total'}
EXACT = {'invoice_number', 'po_number', 'faktur_number', 'vendor_npwp', 'buyer_npwp', 'account_number',
         'invoice_date', 'due_date', 'faktur_date', 'currency'}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_grader():
    path = ROOT / 'prototype' / 'evals' / 'invoice_robustness' / 'evaluate.py'
    spec = importlib.util.spec_from_file_location('robustness_evaluate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def media_type_of(data: bytes):
    return next((media for media, magic in MEDIA_TYPES.items() if data.startswith(magic)), None)


def endpoint_reachable(timeout=20) -> bool:
    """TLS handshake only, no AWS request: refuse to spend reservations on a dead connection."""
    try:
        with socket.create_connection((ENDPOINT, 443), timeout=timeout) as raw:
            with ssl.create_default_context().wrap_socket(raw, server_hostname=ENDPOINT):
                return True
    except OSError:
        return False


class Runner:
    """Runs documents one by one and stops spending once the ledger, access or the network says stop."""

    def __init__(self, client):
        self.client, self.network_streak, self.halted = client, 0, None

    def run(self, data, media_type, case_id, document_id):
        record = {'case_id': case_id, 'document_id': document_id, 'media_type': media_type}
        if self.halted:
            return record | {'status': 'NOT_RUN', 'reason': 'halted_' + self.halted, 'attempt_runs': []}
        try:
            trace = self.client.extract_document(data, media_type, case_id)
            extraction = self.client.normalize(trace, document_id)
        except BudgetError:
            self.halted = 'budget'
            return record | {'status': 'ERROR', 'reason': 'budget', 'message': 'Ledger refused the reservation.',
                             'attempt_runs': []}
        except BedrockError as error:
            if error.reason in NETWORK_REASONS:
                self.network_streak += 1
                if self.network_streak >= 2:
                    self.halted = 'network'
            elif error.reason in HALTING_REASONS:
                self.halted = error.reason
            return record | {'status': 'ERROR', 'reason': error.reason, 'message': str(error),
                             'attempt_runs': error.attempt_runs, 'rejected_responses': error.responses}
        except LiveError as error:
            return record | {'status': 'ERROR', 'reason': 'invalid_output', 'message': str(error), 'attempt_runs': []}
        self.network_streak = 0
        return record | {'status': 'COMPLETED', 'trace': trace, 'extraction': extraction,
                         'attempt_runs': trace['attempt_runs']}


# ----- comparisons: three separate claims ------------------------------------------------------------------------

def same(path, want, got):
    if want is None or got is None:
        return want is None and got is None
    name = path.rsplit('.', 1)[-1]
    if name in AMOUNTS:
        try:
            return Decimal(str(want)) == Decimal(str(got))
        except InvalidOperation:
            return False
    if name in EXACT:
        return want == got
    return normalized_text(str(want)) == normalized_text(str(got))


def outcome(path, want, got):
    """Claim 1 split four ways. A blank is held by the rules until Finance fills it; a wrong or invented value is the
    dangerous case, and one boolean used to hide the difference."""
    if got is None:
        return 'absent' if want is None else 'blank'
    if want is None:
        return 'invented'
    return 'correct' if same(path, want, got) else 'wrong'


def compare_outcomes(expected: dict, actual: dict) -> dict:
    """Only the keys the expectation states. Amounts as Decimal, identifiers and dates exact, other text by
    whitespace-normalized equality. vendor_id and line_number are contract fields, not document values."""
    outcomes = {}
    for key, want in expected.items():
        if key in ('vendor_id', 'line_items'):
            continue
        if key == 'payment':
            for sub, value in want.items():
                outcomes['payment.' + sub] = outcome(sub, value, (actual.get('payment') or {}).get(sub))
        else:
            outcomes[key] = outcome(key, want, actual.get(key))
    if 'line_items' in expected:
        rows = actual.get('line_items') or []
        outcomes['line_items.count'] = 'correct' if len(rows) == len(expected['line_items']) else 'wrong'
        for index, item in enumerate(expected['line_items']):
            for key, want in item.items():
                if key != 'line_number':
                    outcomes[f'line_items[{index}].{key}'] = (outcome(key, want, rows[index].get(key))
                                                             if index < len(rows) else 'blank')
    return outcomes


def compare_invoice(expected: dict, actual: dict) -> dict:
    """Claim 1, values: a field is right when it reads the document value, or stays empty where the document has none."""
    return {path: result in ('correct', 'absent') for path, result in compare_outcomes(expected, actual).items()}


def precision_summary(outcome_sets):
    """Precision over the values the model filled in; coverage over the values the document actually holds."""
    tally = Counter(result for outcomes in outcome_sets for result in outcomes.values())
    filled = tally['correct'] + tally['wrong'] + tally['invented']
    on_document = tally['correct'] + tally['wrong'] + tally['blank']
    return {key: tally[key] for key in ('correct', 'absent', 'blank', 'wrong', 'invented')} | {
        'precision': round(tally['correct'] / filled, 4) if filled else None,
        'coverage': round((tally['correct'] + tally['wrong']) / on_document, 4) if on_document else None}


def latency_summary(rows, target_ms=15_000):
    """rows: (duration_ms, page_count). The brief caps one document at 15 s, so the share within target is reported next
    to the median, the nearest-rank p95 and the maximum, overall and per page count."""
    if not rows:
        return None

    def part(values):
        values = sorted(values)
        return {'n': len(values), 'median': round(statistics.median(values)), 'max': values[-1],
                'within_target': sum(value <= target_ms for value in values)}

    durations = sorted(ms for ms, _ in rows)
    pages = sorted({count for _, count in rows})
    return part(durations) | {'p95': durations[max(0, -(-95 * len(durations) // 100) - 1)], 'min': durations[0],
                              'target_ms': target_ms,
                              'by_pages': {count: part(ms for ms, n in rows if n == count) for count in pages}}


def evidence_completeness(extraction: dict) -> dict:
    """Claim 2, sources: every non-null scalar field (vendor_id and line_number excluded) cites a quote."""
    present = [path for path, value in field_values(extraction['invoice']) if value is not None]
    missing = [path for path in present if not extraction['source_evidence'].get(path)]
    return {'non_null_fields': len(present), 'with_evidence': len(present) - len(missing), 'missing': missing}


def text_layer_check(extraction: dict, data: bytes, media_type):
    """Quotes found on the cited page of the PDF text layer, searched as the app validator does. None for images
    and scans, which have no text layer (the app sends those to visual review)."""
    if media_type != 'application/pdf':
        return None
    with pymupdf.open(stream=data, filetype='pdf') as document:
        pages = [normalized_text(page.get_text()) for page in document]
    if not any(pages):
        return None
    entries = [(path, entry) for path, entry in extraction['source_evidence'].items() if entry]
    missing = [path for path, entry in entries if not (1 <= entry['page'] <= len(pages) and re.search(
        rf"(?<!\w){re.escape(normalized_text(entry['raw_value']))}(?!\w)", pages[entry['page'] - 1]))]
    return {'quotes': len(entries), 'found_on_cited_page': len(entries) - len(missing), 'not_found': missing}


def generic(path: str) -> str:
    return re.sub(r'\[\d+\]', '[]', path)


def per_field(check_sets):
    totals, correct = Counter(), Counter()
    for checks in check_sets:
        for path, ok in checks.items():
            totals[generic(path)] += 1
            correct[generic(path)] += bool(ok)
    return {key: {'correct': correct[key], 'total': totals[key]} for key in sorted(totals)}


def accuracy(check_sets):
    values = [ok for checks in check_sets for ok in checks.values()]
    return {'correct': sum(values), 'total': len(values),
            'rate': round(sum(values) / len(values), 4) if values else None}


def metrics(records):
    done = [r for r in records if r['status'] == 'COMPLETED']
    runs = [run for r in records for run in r.get('attempt_runs') or []]
    measured = [usage_cost(run['usage']) for run in runs if run.get('usage')]
    latencies = sorted(r['trace']['duration_ms'] for r in done)
    per_doc = [sum((usage_cost(run['usage']) for run in r['attempt_runs']), Decimal(0)) for r in done]
    return {'documents': len(records), 'completed': len(done),
            'errors': dict(Counter(r['reason'] for r in records if r['status'] != 'COMPLETED')),
            'paid_attempts': len(runs), 'documents_retried': sum(len(r.get('attempt_runs') or []) > 1 for r in records),
            'latency_ms': {'median': round(statistics.median(latencies)), 'max': latencies[-1],
                           'min': latencies[0]} if latencies else None,
            'tokens': {'input_total': sum(run['usage']['input_tokens'] for run in runs if run.get('usage')),
                       'output_total': sum(run['usage']['output_tokens'] for run in runs if run.get('usage')),
                       'input_per_completed_doc_median': round(statistics.median(
                           r['trace']['usage']['input_tokens'] for r in done)) if done else None,
                       'output_per_completed_doc_median': round(statistics.median(
                           r['trace']['usage']['output_tokens'] for r in done)) if done else None,
                       'output_per_completed_doc_max': max(
                           r['trace']['usage']['output_tokens'] for r in done) if done else None},
            'cost_usd_from_measured_tokens': {
                'all_attempts_total': str(sum(measured, Decimal(0))),
                'per_completed_doc_mean': str(sum(per_doc, Decimal(0)) / len(per_doc)) if per_doc else None,
                'per_completed_doc_max': str(max(per_doc)) if per_doc else None},
            'adaptations': dict(Counter(note.split(':')[0] for r in done for note in r['trace']['adaptations'])),
            'latency_target': latency_summary([(r['trace']['duration_ms'], len(r['trace'].get('pages') or []))
                                               for r in done])}


def grader_summary(results, reasons):
    """Claim 3 for Set A, status: the unchanged grader's verdicts, plus why a case failed."""
    cases = []
    for result in results:
        if result.get('execution') != 'COMPLETED':
            why = 'provider ' + str(reasons.get(result['case_id']) or result.get('execution'))
        else:
            parts = []
            if not result['fields']['passed']:
                parts.append('field ' + ', '.join(result['fields']['mismatched_fields'][:6]))
            if not result['evidence']['passed']:
                parts.append('evidence ' + ', '.join(sorted({f"{e['reason']} {e['field']}"
                                                             for e in result['evidence']['errors']})[:4]))
            if not result['validation_passed']:
                parts.append('status ' + result['actual_status'] + ' ' + ','.join(result['blocking_checks']))
            why = '; '.join(parts)
        cases.append({'case_id': result['case_id'], 'passed': result['passed'], 'why': why})
    completed = [r for r in results if r.get('execution') == 'COMPLETED']
    return {'total': len(results), 'strict_pass': sum(r['passed'] for r in results),
            'fields_pass': sum(r['fields']['passed'] for r in completed),
            'evidence_pass': sum(r['evidence']['passed'] for r in completed),
            'workflow_pass': sum(r['validation_passed'] for r in completed),
            'evidence_errors': dict(Counter(e['reason'] for r in completed for e in r['evidence']['errors'])),
            'cases': cases}


# ----- running ----------------------------------------------------------------------------------------------------

def provenance(client):
    return {'model': client.model, 'prompt_version': PROMPT_VERSION,
            'prompt_sha256': sha256(PROMPT.encode()),
            'parameters': {'provider': 'bedrock', 'region': REGION, **request_profile(),
                           'v1_projection': 'schema v2 metadata keys removed before grading; robustness-v1 has '
                                            'no ground truth for them'}}


def project_v1(extraction):
    projected = deepcopy(extraction)
    for key in METADATA_FIELDS:
        projected['invoice'].pop(key, None)
        projected['source_evidence'].pop(key, None)
    return projected


def save_trace(folder, name, record):
    folder.mkdir(parents=True, exist_ok=True)
    kept = {key: value for key, value in record.items() if key != 'extraction'}
    (folder / (re.sub(r'[^A-Za-z0-9_.-]', '_', name) + '.json')).write_text(
        json.dumps(kept, indent=1, ensure_ascii=False), encoding='utf-8')


def run_set_a(runner, grader, out):
    cases, _ = grader.load_cases()  # verifies the frozen dataset and every PDF hash first
    predictions, prov = [], provenance(runner.client)
    for case in (case for case in cases if case['split'] in grader.DEV_SPLITS):
        data = (ROOT / case['input']['pdf']).read_bytes()
        if sha256(data) != case['input']['pdf_sha256']:
            raise SystemExit('Dataset PDF changed during the run: ' + case['case_id'])
        record = runner.run(data, 'application/pdf', 'eval-a:' + case['case_id'], case['input']['document_id'])
        save_trace(out / 'traces', 'A-' + case['case_id'], record)
        completed = record['status'] == 'COMPLETED'
        predictions.append({'case_id': case['case_id'], 'input_sha256': case['input']['pdf_sha256'],
                            'execution': 'COMPLETED' if completed else 'ERROR',
                            'extraction': project_v1(record['extraction']) if completed else None,
                            'provenance': prov, 'duration_ms': record['trace']['duration_ms'] if completed else None,
                            'cost_usd': record['trace']['cost_upper_estimate_usd'] if completed else None,
                            'error_reason': record.get('reason')})
        print(f"A {case['case_id']}: {record['status']} {record.get('reason') or ''}", flush=True)
    path = out / 'robustness-predictions.jsonl'
    path.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in predictions), encoding='utf-8')
    return predictions


def grade_set_a(grader, predictions, destination):
    """The grade path of evaluate.py main(), pointed at our folder: its CLI only writes under output/evaluation."""
    with patch.object(socket, 'socket', side_effect=RuntimeError('Network disabled in offline evaluation')):
        cases, manifest = grader.load_cases()
        before = grader.budget_snapshot()
        results = grader.grade_saved(cases, predictions)
        after = grader.budget_snapshot()
        if before != after:
            raise RuntimeError('OpenAI ledger changed during grading; investigate concurrent activity.')
        grader.write_report({
            'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'mode': 'SAVED_PROVIDER_OUTPUTS',
            'ocr_quality_verdict': 'INCONCLUSIVE', 'dataset_sha256': manifest['dataset_sha256'],
            'metadata': grader.source_metadata(), 'execution_model': 'SEE_REPORTED_RECORD_PROVENANCE',
            'results': results, 'mutation_controls': [], 'split_counts': dict(Counter(r['split'] for r in results)),
            'holdout_not_run': sum(c['split'] == 'holdout' for c in cases), 'candidate_comparison': 'NOT_RUN',
            'live_ocr_calls': 0, 'budget_before': before, 'budget_after': after, 'budget_unchanged': True},
            destination)
    return results


def manifest_entries(manifest_path: Path, base: Path, allowed: Path):
    """(entry, path or None, skip reason or None) for each listed document."""
    rows = []
    for entry in json.loads(manifest_path.read_text(encoding='utf-8')):
        relative = entry.get('pdf') or entry.get('file')
        if not isinstance(relative, str):
            rows.append((entry, None, 'no_path'))
            continue
        candidates = [(base / relative).resolve(), (base / Path(relative).name).resolve(), (ROOT / relative).resolve()]
        path = next((c for c in candidates if c.is_file() and c.is_relative_to(allowed)), None)
        rows.append((entry, path, None if path else 'missing_file'))
    return rows


def set_b_rows(only=None):
    """Manifest rows, optionally limited to the named files in the given order (to fit the ledger)."""
    rows = manifest_entries(DEMO_MANIFEST, ROOT, ROOT / 'output' / 'pdf')
    if not only:
        return rows
    by_name = {Path(str(entry.get('pdf') or entry.get('file'))).name: (entry, path, skip) for entry, path, skip in rows}
    unknown = [name for name in only if name not in by_name]
    if unknown:
        raise SystemExit('Not in demo-final manifest: ' + ', '.join(unknown))
    return [by_name[name] for name in only]


def run_set_b(runner, out, only=None):
    skipped = []
    for entry, path, skip in set_b_rows(only):
        name = path.name if path else str(entry.get('pdf') or entry.get('file'))
        data = path.read_bytes() if path else b''
        media = media_type_of(data) if path else None
        reason = skip or ('hash_mismatch' if entry.get('sha256') and sha256(data) != entry['sha256'] else None) \
            or (None if media else 'unsupported_type')
        if reason:
            skipped.append({'file': name, 'reason': reason})
            print(f'B {name}: SKIPPED {reason}', flush=True)
            continue
        record = runner.run(data, media, 'eval-b:' + name, 'demo-final.' + path.stem)
        save_trace(out / 'traces', 'B-' + name, record)
        print(f'B {name}: {record["status"]} {record.get("reason") or ""}', flush=True)
    return skipped


def planned_set_b(only=None):
    return sum(1 for _, path, _ in set_b_rows(only) if path)


def shown(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def eval_ledger(cap: Decimal, path: Path = EVAL_LEDGER):
    ledger = BudgetLedger(path, cap, RESERVATION_MICRO_USD)
    if not path.exists():
        ledger.initialize()
    return ledger


def ready_client(ledger, planned: int):
    client = BedrockClient(BedrockConfig.load(), ledger)
    preflight = client.preflight()  # BudgetError when blocked or exhausted
    if preflight['remaining_calls'] < planned:
        raise SystemExit(f'Eval ledger covers {preflight["remaining_calls"]} attempts, {planned} documents planned. '
                         'Nothing was sent. Raise --cap-usd (max 2.00) or run fewer sets.')
    if not endpoint_reachable():
        raise SystemExit('Bedrock endpoint unreachable (TLS handshake failed). Nothing was sent.')
    return client


# ----- offline analysis and reports -------------------------------------------------------------------------------

def analyze_document(record, expected, data):
    doc = {'status': record['status'], 'reason': record.get('reason'), 'media_type': record.get('media_type'),
           'attempts': len(record.get('attempt_runs') or [])}
    if record['status'] != 'COMPLETED':
        return doc
    trace = record['trace']
    extraction = normalize_payload(trace['payload'], record['document_id'])
    invoice = extraction['invoice']
    return doc | {'duration_ms': trace['duration_ms'], 'usage': trace['usage'], 'adaptations': trace['adaptations'],
                  'checks': compare_invoice(expected, invoice) if isinstance(expected, dict) else None,
                  'outcomes': compare_outcomes(expected, invoice) if isinstance(expected, dict) else None,
                  'pages': len(trace.get('pages') or []),
                  'evidence': evidence_completeness(extraction),
                  'text_layer': text_layer_check(extraction, data, record.get('media_type')),
                  'faktur_filled': bool(invoice.get('faktur_number') or invoice.get('faktur_date'))}


def aggregate(docs, records):
    done = [d for d in docs if d['status'] == 'COMPLETED']
    checks = [d['checks'] for d in done if d.get('checks')]
    evidence = [d['evidence'] for d in done]
    layers = [d['text_layer'] for d in done if d.get('text_layer')]
    return {'documents': len(docs), 'completed': len(done),
            'field_accuracy': accuracy(checks), 'per_field': per_field(checks),
            'documents_all_fields_correct': sum(all(c.values()) for c in checks),
            'evidence_completeness': {
                'with_evidence': sum(e['with_evidence'] for e in evidence),
                'non_null_fields': sum(e['non_null_fields'] for e in evidence),
                'documents_complete': sum(not e['missing'] for e in evidence),
                'missing_by_field': dict(Counter(generic(p) for e in evidence for p in e['missing']).most_common())},
            'evidence_on_text_layer': {
                'found': sum(t['found_on_cited_page'] for t in layers), 'quotes': sum(t['quotes'] for t in layers),
                'documents_checked': len(layers), 'documents_all_found': sum(not t['not_found'] for t in layers)},
            'faktur_filled': sum(d['faktur_filled'] for d in done),
            'field_outcomes': precision_summary([d['outcomes'] for d in done if d.get('outcomes')]),
            'metrics': metrics(records)}


def analyze_run(run_dir: Path) -> dict:
    """Every reported number from saved traces, grader output and the expected answers. No API call."""
    meta = json.loads((run_dir / 'results.json').read_text(encoding='utf-8')) if (run_dir / 'results.json').is_file() \
        else {}
    cases = {c['case_id']: c for c in map(json.loads, CASES.read_text(encoding='utf-8').splitlines())}
    manifest = {Path(str(e.get('pdf') or e.get('file'))).name: e
                for e in json.loads(DEMO_MANIFEST.read_text(encoding='utf-8'))}
    pairs = {'A': [], 'B': []}
    for path in sorted((run_dir / 'traces').glob('*.json')):
        record = json.loads(path.read_text(encoding='utf-8'))
        prefix, _, name = record['case_id'].partition(':')
        if prefix == 'eval-a':
            case = cases[name]
            doc = analyze_document(record, case['expected_behavior']['invoice'],
                                   (ROOT / case['input']['pdf']).read_bytes())
            pairs['A'].append(({'case_id': name} | doc, record))
        elif prefix == 'eval-b':
            entry = manifest.get(name, {})
            doc = analyze_document(record, entry.get('expected_invoice'), (DEMO_MANIFEST.parent / name).read_bytes())
            pairs['B'].append(({'file': name} | doc, record))
    analysis = {'run_dir': shown(run_dir), 'generated_at_utc': meta.get('generated_at_utc'),
                'prompt_version': meta.get('prompt_version'), 'prompt_sha256': meta.get('prompt_sha256'),
                'model': meta.get('model'), 'set_b_selection': meta.get('set_b_selection'),
                'set_b_skipped': meta.get('set_b_skipped', []), 'ledger': meta.get('ledger')}
    if pairs['A']:
        order = list(cases)
        docs = sorted(pairs['A'], key=lambda pair: order.index(pair[0]['case_id']))
        part = aggregate([d for d, _ in docs], [r for _, r in docs])
        results = json.loads((run_dir / 'robustness' / 'results.json').read_text(encoding='utf-8'))['results']
        part['grader'] = grader_summary(results, {d['case_id']: d.get('reason') for d, _ in docs})
        part['documents'] = [d for d, _ in docs]
        analysis['set_a'] = part
    if pairs['B']:
        selection = analysis['set_b_selection'] if isinstance(analysis['set_b_selection'], list) else []
        docs = sorted(pairs['B'], key=lambda pair: (selection.index(pair[0]['file'])
                                                    if pair[0]['file'] in selection else 99, pair[0]['file']))
        part = aggregate([d for d, _ in docs], [r for _, r in docs])
        part['documents'] = [d for d, _ in docs]
        analysis['set_b'] = part
    analysis['totals'] = metrics([r for group in pairs.values() for _, r in group])
    return analysis


def pct(part):
    return f"{part['correct']}/{part['total']} ({part['correct'] / part['total']:.1%})" if part['total'] else '-'


def ratio(found, total):
    return f'{found}/{total} ({found / total:.1%})' if total else '-'


def usd(value):
    return 'US$' + (f'{Decimal(value):.4f}' if value is not None else '-')


def share(value):
    return f'{value:.1%}' if value is not None else '-'


def counts(mapping):
    return ', '.join(f'{key} {value}' for key, value in mapping.items()) or 'tidak ada'


CLAIMS = ['Tiga klaim dinilai terpisah:', '',
          '- **Field benar**: nilai yang terbaca sama dengan jawaban. Nominal sebagai desimal, nomor dan tanggal persis.',
          '- **Evidence lengkap**: setiap field yang terisi punya kutipan sumber (vendor_id dan line_number tidak '
          'dihitung).',
          '- **Status**: Set A memakai grader lama, yaitu evidence sama dengan anotasi dan status validasi sesuai '
          'harapan. Set B dicek dengan mencari kutipan di teks halaman PDF yang ditunjuk, seperti validator aplikasi.',
          '']


def set_lines(part):
    ev, layer = part['evidence_completeness'], part['evidence_on_text_layer']
    lines = [f"- Field benar: {pct(part['field_accuracy'])}. Dokumen dengan semua field benar: "
             f"{part['documents_all_fields_correct']}/{part['completed']}.",
             f"- Evidence lengkap: {ratio(ev['with_evidence'], ev['non_null_fields'])} field terisi punya kutipan. "
             f"Dokumen dengan evidence lengkap: {ev['documents_complete']}/{part['completed']}.",
             f"- Field tanpa kutipan: {counts(ev['missing_by_field'])}."]
    outcomes, timing = part.get('field_outcomes'), part['metrics'].get('latency_target')
    if outcomes:
        lines.append(f"- Presisi nilai terisi: {share(outcomes['precision'])}. Cakupan nilai dokumen: "
                     f"{share(outcomes['coverage'])}. Kosong {outcomes['blank']}, salah {outcomes['wrong']}, "
                     f"mengarang {outcomes['invented']}.")
    if timing:
        lines.append(f"- Selesai ≤ 15 detik: {timing['within_target']}/{timing['n']}. p50 {timing['median']} ms, "
                     f"p95 {timing['p95']} ms, maks {timing['max']} ms. Per jumlah halaman: " + ', '.join(
                         f"{pages} hal {row['within_target']}/{row['n']} (maks {row['max']} ms)"
                         for pages, row in timing['by_pages'].items()) + '.')
    if layer['documents_checked']:
        lines.append(f"- Kutipan ketemu di teks halaman PDF yang ditunjuk: {ratio(layer['found'], layer['quotes'])}, "
                     f"semua ketemu di {layer['documents_all_found']}/{layer['documents_checked']} PDF ber-teks.")
    if 'grader' in part:
        g = part['grader']
        lines += [f"- Grader: evidence sama dengan anotasi {g['evidence_pass']}/{g['total']}, status validasi sesuai "
                  f"harapan {g['workflow_pass']}/{g['total']}, lulus ketat {g['strict_pass']}/{g['total']}."]
    return lines


def run_lines(analysis, level='##'):
    lines = []
    a, b = analysis.get('set_a'), analysis.get('set_b')
    if a:
        lines += [f"{level} Set A: field benar {pct(a['field_accuracy'])}, evidence lengkap di "
                  f"{a['evidence_completeness']['documents_complete']} dari {a['completed']} kasus", '',
                  'Sepuluh kasus development robustness-v1. Status dari grader deterministik yang tidak diubah.', '']
        lines += set_lines(a) + ['', 'Kasus yang tidak lulus ketat:', '']
        lines += [f"- {r['case_id']}: {r['why']}" for r in a['grader']['cases'] if not r['passed']] or ['- tidak ada']
        lines += ['', 'Metadata v2 (NPWP, PO, faktur) tidak dinilai sebagai field di set ini karena robustness-v1 '
                      f"belum punya jawabannya. Faktur terisi di {a['faktur_filled']} dari {a['completed']} kasus. "
                      'Tidak ada halaman Faktur Pajak di set ini, jadi angka yang benar adalah 0.', '']
    if b:
        lines += [f"{level} Set B: field benar {pct(b['field_accuracy'])}, evidence lengkap di "
                  f"{b['evidence_completeness']['documents_complete']} dari {b['completed']} dokumen", '']
        if isinstance(analysis['set_b_selection'], list):
            lines += [f"File yang dijalankan: {', '.join(analysis['set_b_selection'])}. Pilihan ini menyesuaikan "
                      'sisa reservasi ledger eval.', '']
        lines += set_lines(b) + ['', '| File | Status | Field benar | Evidence | Kutipan di teks PDF | Latensi |',
                                      '|---|---|---|---|---|---|']
        for doc in b['documents']:
            checks, ev, layer = doc.get('checks') or {}, doc.get('evidence'), doc.get('text_layer')
            status = doc['status'] + (' ' + doc['reason'] if doc.get('reason') else '')
            fields = f'{sum(checks.values())}/{len(checks)}' if checks else '-'
            cited = f"{ev['with_evidence']}/{ev['non_null_fields']}" if ev else '-'
            found = f"{layer['found_on_cited_page']}/{layer['quotes']}" if layer else 'gambar, tanpa teks'
            latency = f"{doc['duration_ms']} ms" if 'duration_ms' in doc else '-'
            lines.append(f"| {doc['file']} | {status} | {fields} | {cited} | {found} | {latency} |")
        wrong = {k: v for k, v in b['per_field'].items() if v['correct'] < v['total']}
        lines += ['', 'Field yang tidak selalu benar: ' + (', '.join(f"{k} {v['correct']}/{v['total']}"
                                                                  for k, v in wrong.items()) or 'tidak ada') + '.', '']
    return lines


def cost_lines(analysis):
    lines = ['| Set | Dokumen selesai | Percobaan berbayar | Latensi median / maks | Token output median / maks | '
             'Biaya rata-rata / maks per dokumen |', '|---|---|---|---|---|---|']
    for label in ('set_a', 'set_b'):
        part = analysis.get(label)
        if part:
            m = part['metrics']
            lat, tok, cost = m['latency_ms'] or {}, m['tokens'], m['cost_usd_from_measured_tokens']
            lines.append(f"| {label[-1].upper()} | {m['completed']}/{m['documents']} | {m['paid_attempts']} | "
                         f"{lat.get('median', '-')} / {lat.get('max', '-')} ms | "
                         f"{tok['output_per_completed_doc_median']} / {tok['output_per_completed_doc_max']} | "
                         f"{usd(cost['per_completed_doc_mean'])} / {usd(cost['per_completed_doc_max'])} |")
    return lines


LIMITS = ['## Batasan', '',
          '- Variasi antar-run dengan prompt yang sama belum diukur. Temperature 0 tidak menjamin hasil identik.',
          '- Dataset satu keluarga template sintetis. Belum mewakili invoice klien AMIGA.',
          '- Latensi diukur dari laptop. Angkanya sudah termasuk render PDF, jaringan, dan percobaan ulang.',
          f'- Harga batas atas US${PRICE_INPUT_PER_M}/US${PRICE_OUTPUT_PER_M} per 1 juta token input/output, dicek '
          f'{PRICE_VERIFIED}. Biaya di sini dari token terukur, bukan tagihan AWS.',
          '- Adaptasi deterministik (lihat `results.json`) tidak pernah mengubah nilai yang terbaca dari halaman.', '']


def write_run_report(out: Path, analysis: dict):
    totals = analysis['totals']
    lines = ['# Evaluasi Bedrock Nova 2 Lite pada invoice sintetis', '',
             f"Run {str(analysis['generated_at_utc'])[:16].replace('T', ' ')} UTC. Model `{analysis['model']}`, region "
             f"{REGION}, prompt `{analysis['prompt_version']}` (sha256 `{str(analysis['prompt_sha256'])[:12]}`).", '',
             'Semua dokumen sintetis. Holdout robustness tidak dikirim. Satu run, temperature 0.', ''] + CLAIMS
    lines += run_lines(analysis) + ['## Biaya dari token terukur', ''] + cost_lines(analysis)
    lines += ['', f"Total: {totals['paid_attempts']} percobaan berbayar, "
                  f"{usd(totals['cost_usd_from_measured_tokens']['all_attempts_total'])}. Adaptasi terpakai: "
                  f"{counts(totals['adaptations'])}.", ''] + LIMITS
    lines += ['Rincian per dokumen ada di `results.json`, trace di `traces/`, laporan grader di `robustness/`.']
    (out / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_comparison(report: Path, analyses):
    def row(label, value):
        return f'| {label} | ' + ' | '.join(value(a) for a in analyses) + ' |'

    def part(name, fn):
        return lambda a: fn(a[name]) if a.get(name) else '-'

    head = ['Ukuran'] + [f'Run {i}' for i in range(1, len(analyses) + 1)]
    lines = ['# Evaluasi Bedrock Nova 2 Lite: run berdampingan', '',
             'Dokumen dan kode sama di semua run. Yang berbeda hanya PROMPT bersama dari `openai_live.py`. Versi '
             'prompt tetap `amiga-doc-extract.v2`, jadi run dibedakan lewat hash.', ''] + CLAIMS
    lines += ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head),
              row('Waktu run (UTC)', lambda a: str(a['generated_at_utc'])[:16].replace('T', ' ')),
              row('Prompt sha256', lambda a: f"`{str(a['prompt_sha256'])[:12]}`"),
              row('Set A field benar', part('set_a', lambda p: pct(p['field_accuracy']))),
              row('Set A kasus dengan semua field benar',
                  part('set_a', lambda p: f"{p['documents_all_fields_correct']}/{p['completed']}")),
              row('Set A field terisi yang punya kutipan', part('set_a', lambda p: ratio(
                  p['evidence_completeness']['with_evidence'], p['evidence_completeness']['non_null_fields']))),
              row('Set A kasus dengan evidence lengkap',
                  part('set_a', lambda p: f"{p['evidence_completeness']['documents_complete']}/{p['completed']}")),
              row('Set A evidence sama dengan anotasi (grader)',
                  part('set_a', lambda p: f"{p['grader']['evidence_pass']}/{p['grader']['total']}")),
              row('Set A status validasi sesuai harapan',
                  part('set_a', lambda p: f"{p['grader']['workflow_pass']}/{p['grader']['total']}")),
              row('Set A lulus ketat', part('set_a', lambda p: f"{p['grader']['strict_pass']}/{p['grader']['total']}")),
              row('Set B field benar', part('set_b', lambda p: pct(p['field_accuracy']))),
              row('Set B field terisi yang punya kutipan', part('set_b', lambda p: ratio(
                  p['evidence_completeness']['with_evidence'], p['evidence_completeness']['non_null_fields']))),
              row('Set B dokumen dengan evidence lengkap',
                  part('set_b', lambda p: f"{p['evidence_completeness']['documents_complete']}/{p['completed']}")),
              row('Set B kutipan ketemu di teks PDF', part('set_b', lambda p: ratio(
                  p['evidence_on_text_layer']['found'], p['evidence_on_text_layer']['quotes']))),
              row('Dokumen selesai', lambda a: f"{a['totals']['completed']}/{a['totals']['documents']}"),
              row('Percobaan berbayar', lambda a: str(a['totals']['paid_attempts'])),
              row('Biaya dari token terukur',
                  lambda a: usd(a['totals']['cost_usd_from_measured_tokens']['all_attempts_total'])),
              row('Latensi median / maks', lambda a: f"{a['totals']['latency_ms']['median']} / "
                                                     f"{a['totals']['latency_ms']['max']} ms"
                  if a['totals']['latency_ms'] else '-'), '']
    for index, analysis in enumerate(analyses, 1):
        lines += [f"## Run {index}: `{analysis['run_dir']}`", ''] + run_lines(analysis, '###')
        lines += ['Biaya dari token terukur:', ''] + cost_lines(analysis) + ['']
    lines += LIMITS + ['Rincian tiap run ada di `results.json`, `traces/` dan `robustness/` pada folder run-nya.']
    report.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def synthetic(args):
    out = args.output.resolve()
    if not any(out.is_relative_to(root) for root in OUTPUT_ROOTS):
        raise SystemExit('Synthetic results stay under output/app-stage6 or output/app-stage8.')
    if (out / 'results.json').exists() or (out / 'traces').exists() or ('A' in args.sets and (out / 'robustness').exists()):
        raise SystemExit('Output already holds a run; choose a new --output. Nothing was sent.')
    grader = load_grader() if 'A' in args.sets else None
    if grader:
        grader.load_cases()
    planned = (10 if 'A' in args.sets else 0) + (planned_set_b(args.b_files) if 'B' in args.sets else 0)
    ledger = eval_ledger(args.cap_usd, args.ledger)
    before = ledger.snapshot()
    runner = Runner(ready_client(ledger, planned))
    out.mkdir(parents=True, exist_ok=True)
    meta = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'model': runner.client.model,
            'region': REGION, 'prompt_version': PROMPT_VERSION, 'prompt_sha256': sha256(PROMPT.encode()),
            'request_profile': request_profile(), 'price_per_million_usd':
                {'input': str(PRICE_INPUT_PER_M), 'output': str(PRICE_OUTPUT_PER_M), 'verified': PRICE_VERIFIED},
            'planned_documents': planned, 'set_b_selection': args.b_files or 'all existing manifest files'}
    if 'A' in args.sets:
        grade_set_a(grader, run_set_a(runner, grader, out), out / 'robustness')
    if 'B' in args.sets:
        meta['set_b_skipped'] = run_set_b(runner, out, args.b_files)
    meta.update(halted=runner.halted, ledger={'path': shown(args.ledger), 'cap_usd': str(args.cap_usd),
                                              'before': before, 'after': ledger.snapshot()})
    (out / 'results.json').write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding='utf-8')
    analysis = analyze_run(out)
    (out / 'results.json').write_text(json.dumps(meta | {'analysis': analysis}, indent=1, ensure_ascii=False),
                                      encoding='utf-8')
    write_run_report(out, analysis)
    print(json.dumps({key: analysis[key]['field_accuracy'] for key in ('set_a', 'set_b') if key in analysis} | {
        'evidence_complete_docs': {key: analysis[key]['evidence_completeness']['documents_complete']
                                   for key in ('set_a', 'set_b') if key in analysis},
        'set_a_strict_pass': analysis.get('set_a', {}).get('grader', {}).get('strict_pass'),
        'paid_attempts': analysis['totals']['paid_attempts'],
        'measured_cost_usd': analysis['totals']['cost_usd_from_measured_tokens']['all_attempts_total'],
        'halted': runner.halted, 'remaining_calls': meta['ledger']['after']['remaining_calls']}, indent=1))
    return 0


def compare(args):
    report = (args.report or DEFAULT_OUTPUT / 'REPORT.md').resolve()
    if not any(report.is_relative_to(root) for root in OUTPUT_ROOTS):
        raise SystemExit('The comparison report stays under output/app-stage6 or output/app-stage8.')
    report.parent.mkdir(parents=True, exist_ok=True)
    analyses = [analyze_run(Path(run).resolve()) for run in args.compare]
    write_comparison(report, analyses)
    (report.parent / 'comparison.json').write_text(json.dumps(analyses, indent=1, ensure_ascii=False),
                                                   encoding='utf-8')
    print('Wrote ' + shown(report))
    return 0


def real_case(args):
    folder = args.real_case.resolve()
    if not folder.is_dir():
        raise SystemExit('--real-case expects a folder.')
    if (folder / 'manifest.json').is_file():
        rows = manifest_entries(folder / 'manifest.json', folder, folder)
    else:
        rows = [({}, path, None) for path in sorted(folder.iterdir())
                if path.is_file() and path.suffix.lower() in ('.pdf', '.jpg', '.jpeg', '.png')]
    destination = REAL_CASE_OUTPUT / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    runner = Runner(ready_client(eval_ledger(args.cap_usd, args.ledger), sum(1 for _, path, _ in rows if path)))
    details, records, docs, skipped = [], [], [], 0
    for index, (entry, path, skip) in enumerate(rows, 1):
        data = path.read_bytes() if path else b''
        media = media_type_of(data) if path else None
        if skip or media is None or (entry.get('sha256') and sha256(data) != entry['sha256']):
            skipped += 1
            details.append({'index': index, 'file': path.name if path else None, 'status': 'SKIPPED'})
            continue
        # Case and document IDs carry no file names: the eval ledger lives outside .appdata.
        record = runner.run(data, media, f'real-case:{index}', f'real-case.{index}')
        doc = analyze_document(record, entry.get('expected_invoice'), data)
        details.append({'index': index, 'file': path.name, 'analysis': doc, **record})
        records.append(record)
        docs.append(doc)
    destination.mkdir(parents=True, exist_ok=False)
    summary = aggregate(docs, records)
    (destination / 'results.json').write_text(json.dumps({'summary': summary, 'details': details}, indent=1,
                                                         ensure_ascii=False, default=str), encoding='utf-8')
    print(json.dumps({'documents': len(rows), 'skipped': skipped, 'completed': summary['completed'],
                      'errors': summary['metrics']['errors'], 'field_accuracy': summary['field_accuracy'],
                      'evidence_completeness': {k: v for k, v in summary['evidence_completeness'].items()
                                                if k != 'missing_by_field'},
                      'field_outcomes': summary['field_outcomes'], 'per_field': summary['per_field'],
                      'latency_ms': summary['metrics']['latency_ms'],
                      'latency_target': summary['metrics']['latency_target'], 'tokens': summary['metrics']['tokens'],
                      'cost_usd': summary['metrics']['cost_usd_from_measured_tokens'], 'halted': runner.halted,
                      'details_folder': shown(destination)}, indent=1))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sets', choices=('A', 'B', 'AB'), default='AB')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--ledger', type=Path, default=EVAL_LEDGER,
                        help='eval ledger file; stage 8 uses its own so the stage 6 ledger stays untouched')
    parser.add_argument('--cap-usd', type=Decimal, default=EVAL_CAP_USD,
                        help='eval ledger cap; reservations are cumulative across runs (max 2.00)')
    parser.add_argument('--b-files', type=lambda text: [name.strip() for name in text.split(',') if name.strip()],
                        help='comma-separated demo-final file names to run, in this order (default: all)')
    parser.add_argument('--compare', nargs='+', metavar='RUN_DIR', help='offline: side-by-side report of saved runs')
    parser.add_argument('--report', type=Path, help='with --compare: report path (default bedrock-eval/REPORT.md)')
    parser.add_argument('--real-case', type=Path, help='folder of REAL invoices; details only under .appdata')
    args = parser.parse_args()
    if not Decimal(0) < args.cap_usd <= MAX_CAP_USD:
        parser.error('--cap-usd must be above 0 and at most 2.00.')
    try:
        if args.compare:
            return compare(args)
        return real_case(args) if args.real_case else synthetic(args)
    except (LiveError, BudgetError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
