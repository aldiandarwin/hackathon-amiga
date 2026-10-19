"""No network. Metrics of the Bedrock eval harness: blank vs wrong values, p95 and the 15 s brief target."""

import importlib.util
from pathlib import Path
import unittest

HARNESS = Path(__file__).resolve().parents[1] / 'evals' / 'bedrock' / 'run_eval.py'
spec = importlib.util.spec_from_file_location('run_eval', HARNESS)
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)


class OutcomeTests(unittest.TestCase):
    def test_outcome_separates_blank_wrong_and_invented_values(self):
        # A blank is held by the rules for Finance; a wrong value is the dangerous case. One number hid both.
        self.assertEqual(run_eval.outcome('stated_total', '100.00', '100'), 'correct')
        self.assertEqual(run_eval.outcome('stated_total', '100.00', None), 'blank')
        self.assertEqual(run_eval.outcome('stated_total', '100.00', '90'), 'wrong')
        self.assertEqual(run_eval.outcome('po_number', None, 'PO-1'), 'invented')
        self.assertEqual(run_eval.outcome('po_number', None, None), 'absent')

    def test_compare_invoice_keeps_the_boolean_field_claim(self):
        # Characterization: the old "field benar" claim must not move when outcomes are added.
        expected = {'stated_total': '100', 'payment': {'account_number': '123'},
                    'line_items': [{'line_number': 1, 'description': 'A', 'quantity': '2'}]}
        actual = {'stated_total': None, 'payment': {'account_number': '123'}, 'line_items': []}
        self.assertEqual(run_eval.compare_invoice(expected, actual),
                         {'stated_total': False, 'payment.account_number': True, 'line_items.count': False,
                          'line_items[0].description': False, 'line_items[0].quantity': False})

    def test_precision_counts_only_filled_values_and_coverage_only_document_values(self):
        summary = run_eval.precision_summary([
            {'a': 'correct', 'b': 'blank', 'c': 'wrong'},
            {'a': 'correct', 'd': 'invented', 'e': 'absent'}])
        self.assertEqual(summary, {'correct': 2, 'absent': 1, 'blank': 1, 'wrong': 1, 'invented': 1,
                                   'precision': 0.5, 'coverage': 0.75})


class LedgerTests(unittest.TestCase):
    def test_eval_ledger_at_a_new_path_starts_with_its_own_budget(self):
        # Stage 8 runs on its own ledger; the exhausted stage 6 ledger must stay untouched.
        from decimal import Decimal
        from uuid import uuid4
        path = run_eval.ROOT / 'prototype' / 'output' / 'test-runtime' / (str(uuid4()) + '.sqlite3')
        before = run_eval.EVAL_LEDGER.stat().st_mtime_ns if run_eval.EVAL_LEDGER.exists() else None
        ledger = run_eval.eval_ledger(Decimal('2.00'), path)
        self.assertEqual(ledger.snapshot()['remaining_calls'], 40)
        self.assertEqual(run_eval.EVAL_LEDGER.stat().st_mtime_ns if run_eval.EVAL_LEDGER.exists() else None, before)


class LatencyTests(unittest.TestCase):
    def test_latency_summary_reports_p95_and_the_share_within_target(self):
        rows = [(ms, 1 if ms <= 10_000 else 5) for ms in range(1_000, 21_000, 1_000)]
        summary = run_eval.latency_summary(rows, target_ms=15_000)
        self.assertEqual({key: summary[key] for key in ('n', 'median', 'p95', 'max', 'within_target')},
                         {'n': 20, 'median': 10_500, 'p95': 19_000, 'max': 20_000, 'within_target': 15})
        self.assertEqual(summary['by_pages'], {1: {'n': 10, 'median': 5_500, 'max': 10_000, 'within_target': 10},
                                               5: {'n': 10, 'median': 15_500, 'max': 20_000, 'within_target': 5}})

    def test_latency_summary_of_nothing_is_none(self):
        self.assertIsNone(run_eval.latency_summary([], target_ms=15_000))


if __name__ == '__main__':
    unittest.main()
