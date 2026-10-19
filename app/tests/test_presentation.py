"""Queue labels must distinguish tax blocks, source review and calculated amounts."""

import unittest

from app.presentation import queue_summary


class QueueSummaryTests(unittest.TestCase):
    def test_open_tax_checks_keep_the_computed_amount_visible(self):
        snapshot = {'tax': {'status': 'COMPUTED', 'net_payable': '4360000.00'},
                    'validation': {'checks': [{'code': 'TAX_PPN_CONFLICT', 'status': 'FAILED', 'blocking': True}]}}
        self.assertEqual(queue_summary(snapshot, 'EXCEPTION')['net_payable'], '4360000.00')
        self.assertEqual(queue_summary(snapshot, 'AMIGA_REVIEWED')['net_payable'], '4360000.00')
        self.assertEqual(queue_summary(snapshot, 'EXCEPTION')['issue_codes'], ['TAX_PPN_CONFLICT'])

    def test_source_checks_remain_distinct_from_automatic_blockers(self):
        snapshot = {'tax': {'status': 'COMPUTED', 'net_payable': '0.00'}, 'validation': {'checks': [
            {'code': 'SOURCE_VALUE_MISMATCH', 'status': 'FAILED', 'blocking': True},
            {'code': 'POSSIBLE_DUPLICATE', 'status': 'FAILED', 'blocking': True},
            {'code': 'POSSIBLE_DUPLICATE', 'status': 'FAILED', 'blocking': True},
            {'code': 'TOTAL_MATCH', 'status': 'PASSED', 'blocking': True}]}}
        shown = queue_summary(snapshot, 'EXCEPTION')
        self.assertEqual(shown['issue_codes'], ['POSSIBLE_DUPLICATE'])
        self.assertEqual(shown['issue_count'], 1)
        self.assertEqual(shown['source_check_count'], 1)
        self.assertEqual(shown['net_payable'], '0.00')
        snapshot['validation']['checks'] = snapshot['validation']['checks'][:1]
        self.assertEqual(queue_summary(snapshot, 'READY_FOR_REVIEW')['net_payable'], '0.00')
        self.assertEqual(queue_summary(snapshot, 'AMIGA_APPROVED')['source_check_count'], 0)

    def test_uncomputed_and_missing_tax_have_no_payment_amount(self):
        self.assertIsNone(queue_summary(None, 'QUEUED')['net_payable'])
        self.assertIsNone(queue_summary({'tax': {'status': 'NOT_COMPUTED', 'net_payable': '4440000.00'}}, 'EXCEPTION')['net_payable'])
