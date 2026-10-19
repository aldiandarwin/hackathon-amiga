"""Grader failure-mode checks. Uses development cases only, no provider or database."""

from copy import deepcopy
import unittest

from .evaluate import load_cases, extraction_for, grade_case, grade_saved, mutation_controls, validate_saved_records


class GraderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, _ = load_cases()
        cls.dev = [c for c in cls.cases if c['split'] != 'holdout']
        cls.first = cls.dev[0]

    def record(self, case=None):
        case = case or self.first
        return {'case_id': case['case_id'], 'input_sha256': case['input']['pdf_sha256'],
            'execution': 'COMPLETED', 'extraction': extraction_for(case),
            'provenance': {'model': 'test-control-not-a-model', 'prompt_version': 'unit.v1',
                           'prompt_sha256': '1' * 64, 'parameters': {'mode': 'UNIT_TEST'}}}

    def test_ideal_development_extractions_and_expected_exceptions(self):
        for case in self.dev:
            with self.subTest(case=case['case_id']):
                self.assertTrue(grade_case(case, extraction_for(case))['passed'])

    def test_twelve_intentional_faults_are_all_rejected(self):
        controls = mutation_controls(self.cases)
        self.assertEqual(len(controls), 12)
        self.assertTrue(all(c['rejected'] for c in controls))

    def test_missing_cases_stay_in_denominator(self):
        results = grade_saved(self.cases, [self.record()])
        self.assertEqual(len(results), 10)
        self.assertEqual(sum(r['execution'] == 'MISSING_OUTPUT' for r in results), 9)
        self.assertEqual(sum(r['passed'] for r in results), 1)

    def test_provider_error_is_not_graded_as_empty_invoice(self):
        record = self.record()
        record.update(execution='ERROR', extraction=None)
        result = grade_saved(self.cases, [record])[0]
        self.assertEqual(result['execution'], 'PROVIDER_EXECUTION_ERROR')
        self.assertFalse(result['passed'])

    def test_duplicate_records_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            validate_saved_records(self.cases, [self.record(), self.record()])

    def test_wrong_input_hash_rejected(self):
        record = self.record()
        record['input_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash'):
            validate_saved_records(self.cases, [record])

    def test_unknown_case_rejected(self):
        record = self.record()
        record['case_id'] = 'not-in-dataset'
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            validate_saved_records(self.cases, [record])

    def test_holdout_locked_without_reading_its_answer(self):
        held = next(c for c in self.cases if c['split'] == 'holdout')
        with self.assertRaisesRegex(ValueError, 'locked holdout'):
            validate_saved_records(self.cases, [{'case_id': held['case_id']}])

    def test_provenance_required(self):
        for key in ('model', 'prompt_version', 'prompt_sha256', 'parameters'):
            record = self.record()
            record['provenance'].pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_saved_records(self.cases, [record])

    def test_decimal_format_can_differ_but_identifiers_cannot(self):
        payload = extraction_for(self.first)
        payload['invoice']['stated_total'] += '0'
        self.assertTrue(grade_case(self.first, payload)['passed'])
        payload['invoice']['invoice_number'] = ' ' + payload['invoice']['invoice_number']
        self.assertFalse(grade_case(self.first, payload)['passed'])

    def test_missing_null_field_is_invalid_not_equal_to_null(self):
        case = next(c for c in self.dev if c['case_id'] == 'amiga.robust.t05.v1')
        payload = extraction_for(case)
        payload['invoice']['payment'].pop('account_number')
        self.assertEqual(grade_case(case, payload)['execution'], 'INVALID_OUTPUT_CONTRACT')

    def test_grading_cannot_mutate_expected_or_actual_payload(self):
        case, payload = deepcopy(self.first), extraction_for(self.first)
        before_case, before_payload = deepcopy(case), deepcopy(payload)
        grade_case(case, payload)
        self.assertEqual(case, before_case)
        self.assertEqual(payload, before_payload)

    def test_repeated_header_can_cite_another_valid_page(self):
        case = next(c for c in self.dev if c['case_id'] == 'amiga.robust.t01.v1')
        payload = extraction_for(case)
        payload['source_evidence']['vendor_name']['page'] = 4
        self.assertTrue(grade_case(case, payload)['passed'])


if __name__ == '__main__':
    unittest.main()
