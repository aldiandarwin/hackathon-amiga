from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import unittest

from amiga_ocr.adapters import MistralAdapter, OCRSpaceAdapter, merge_chunks
from amiga_ocr.cli import run_case
from amiga_ocr.contracts import Actor, ContractError, ProviderError, Rules, validate_extraction
from amiga_ocr.fixtures import CASE_EXPECTATIONS, scenario
from amiga_ocr.pipeline import FixtureExtractor, process_invoice


def process(case, provider="ocr_space", **overrides):
    args = dict(document_id="doc_demo_001", expected_pages=case.expected_pages,
                context=case.context, actor=case.actor, expected_version=case.context.invoice_version)
    args.update(overrides)
    return process_invoice(case.raw_response(provider),
                           OCRSpaceAdapter() if provider == "ocr_space" else MistralAdapter(),
                           FixtureExtractor(case.invoice_payload), **args)


class PipelineTests(unittest.TestCase):
    def test_synthetic_scenario_matrix_both_providers(self):
        for name in CASE_EXPECTATIONS:
            for provider in ("ocr_space", "mistral"):
                with self.subTest(case=name, provider=provider):
                    case, result = run_case(name, provider)
                    codes = {c["code"] for c in result["validation"]["checks"]}
                    self.assertEqual(result["request_status"], case.expected_status)
                    self.assertTrue(set(case.required_codes) <= codes)
                    self.assertEqual(result["review"]["can_approve"], case.expected_status == "READY_FOR_REVIEW")
                    self.assertIsNone(result["review"]["approved_by"])
                    self.assertEqual(result["voucher"]["status"], "NOT_CREATED")
                    self.assertEqual(result["processing"]["live_provider_calls"], 0)

    def test_provider_neutral_invoice_and_validation(self):
        _, cheap = run_case("normal", "ocr_space")
        _, paid = run_case("normal", "mistral")
        self.assertEqual(cheap["invoice"], paid["invoice"])
        self.assertEqual(cheap["validation"], paid["validation"])

    def test_source_and_extraction_are_not_mutated(self):
        case = scenario("normal")
        before = deepcopy(case.invoice_payload)
        raw = case.raw_response("ocr_space")
        raw_before = deepcopy(raw)
        process_invoice(raw, OCRSpaceAdapter(), FixtureExtractor(case.invoice_payload),
                        document_id="doc_demo_001", expected_pages=1, context=case.context)
        self.assertEqual(case.invoice_payload, before)
        self.assertEqual(raw, raw_before)

    def test_leading_zero_and_all_items_preserved(self):
        result = process(scenario("normal"))
        self.assertEqual(result["invoice"]["payment"]["account_number"], "00123456")
        self.assertEqual(len(result["invoice"]["line_items"]), 3)
        self.assertEqual(Decimal(result["validation"]["calculated_total"]), Decimal("500000.00"))

    def test_uploader_cannot_approve_with_finance_role(self):
        case = scenario("normal")
        actor = replace(case.actor, user_id="user_pic")
        result = process(case, actor=actor)
        self.assertFalse(result["review"]["can_approve"])
        self.assertIn("SELF_APPROVAL_FORBIDDEN", result["review"]["blocked_reasons"])

    def test_admin_cannot_approve_even_with_finance_role(self):
        case = scenario("normal")
        actor = replace(case.actor, roles=("SYSTEM_ADMIN", "FINANCE_REVIEWER"))
        result = process(case, actor=actor)
        self.assertFalse(result["review"]["can_approve"])
        self.assertIn("ROLE_NOT_ALLOWED", result["review"]["blocked_reasons"])

    def test_missing_client_assignment_blocks_permission(self):
        case = scenario("normal")
        result = process(case, actor=replace(case.actor, client_ids=("client_demo_b",)))
        self.assertIn("CLIENT_NOT_ASSIGNED", result["review"]["blocked_reasons"])

    def test_absent_actor_and_stale_version_block_permission(self):
        result = process(scenario("normal"), actor=None, expected_version=0)
        self.assertFalse(result["review"]["can_approve"])
        self.assertIn("UNAUTHENTICATED", result["review"]["blocked_reasons"])
        self.assertIn("VERSION_CONFLICT", result["review"]["blocked_reasons"])

    def test_float_amount_rejected_without_coercion(self):
        case = scenario("normal")
        case.invoice_payload["invoice"]["stated_total"] = 500000.0
        result = process(case)
        self.assertEqual(result["request_status"], "EXCEPTION")
        self.assertIsNone(result["invoice"])
        self.assertEqual(result["processing"]["error_code"], "INVALID_EXTRACTION_CONTRACT")

    def test_extractor_cannot_inject_approval_or_vendor_id(self):
        for mutation in ("approved", "vendor_id"):
            with self.subTest(mutation=mutation):
                case = scenario("normal")
                if mutation == "approved":
                    case.invoice_payload["request_status"] = "AMIGA_REVIEWED"
                else:
                    case.invoice_payload["invoice"]["vendor_id"] = "vendor_client_b"
                self.assertEqual(process(case)["processing"]["status"], "FAILED")

    def test_evidence_must_match_document_and_original_page(self):
        for key, value in (("document_id", "doc_other"), ("page", 99)):
            with self.subTest(key=key):
                case = scenario("normal")
                case.invoice_payload["source_evidence"]["invoice_number"][key] = value
                codes = {c["code"] for c in process(case)["validation"]["checks"]}
                self.assertIn("SOURCE_EVIDENCE_INVALID", codes)

    def test_identifier_cannot_drop_leading_zero_in_evidence(self):
        case = scenario("normal")
        case.invoice_payload["invoice"]["payment"]["account_number"] = "123456"
        codes = {c["code"] for c in process(case)["validation"]["checks"]}
        self.assertIn("SOURCE_VALUE_MISMATCH", codes)

    def test_quote_cannot_be_only_a_substring_of_a_longer_account(self):
        case = scenario("normal")
        case.pages[0] = case.pages[0].replace("payment.account_number: 00123456", "payment.account_number: 1001234567")
        result = process(case)
        self.assertEqual(result["request_status"], "EXCEPTION")
        self.assertIn("SOURCE_EVIDENCE_INVALID", {c["code"] for c in result["validation"]["checks"]})

    def test_fractional_amounts_calculated_exactly(self):
        case = scenario("normal")
        item = {"line_number": 1, "description": "Barang fraksional", "quantity": "3",
                "unit_price": "0.10", "stated_line_total": "0.30"}
        invoice = case.invoice_payload["invoice"]
        invoice["line_items"] = [item]
        for key in ("stated_subtotal", "stated_total"):
            invoice[key] = "0.30"
            case.invoice_payload["source_evidence"][key]["raw_value"] = "0.30"
        for key, value in item.items():
            if key != "line_number":
                case.invoice_payload["source_evidence"][f"line_items[0].{key}"] = {
                    "document_id": "doc_demo_001", "page": 1, "raw_value": value, "bbox": None,
                }
        case.pages[0] += "\nBarang fraksional: 3 x 0.10 = 0.30"
        result = process(case)
        self.assertEqual(result["request_status"], "READY_FOR_REVIEW")
        self.assertEqual(result["validation"]["calculated_total"], "0.30")

    def test_invalid_calendar_date_rejected(self):
        case = scenario("normal")
        case.invoice_payload["invoice"]["invoice_date"] = "2026-02-30"
        with self.assertRaises(ContractError):
            validate_extraction(case.invoice_payload)

    def test_ambiguous_number_is_not_guessed(self):
        case = scenario("normal")
        case.pages[0] += "\nAmbiguous total: 1.234"
        case.invoice_payload["source_evidence"]["stated_total"]["raw_value"] = "1.234"
        codes = {c["code"] for c in process(case)["validation"]["checks"]}
        self.assertIn("AMBIGUOUS_VALUE", codes)

    def test_thousands_grouped_rupiah_is_read_but_a_typo_is_not(self):
        # 15 Okt 2026: every amount from a million rupiah up came back AMBIGUOUS_VALUE because it had two dots.
        for printed, expected in (("Rp 66.600.000", set()), ("Rp 7.500.0000", {"AMBIGUOUS_VALUE"})):
            with self.subTest(printed=printed):
                case = scenario("normal")
                case.pages[0] += f"\nTotal: {printed}"
                case.invoice_payload["invoice"]["stated_total"] = "66600000"
                case.invoice_payload["source_evidence"]["stated_total"]["raw_value"] = printed
                checks = process(case)["validation"]["checks"]
                self.assertEqual({c["code"] for c in checks if c["field"] == "stated_total"}, expected)

    def test_other_charges_join_the_total_and_never_pass_as_a_discount(self):
        # 15 Okt 2026: "Biaya tools Rp600.000" below the subtotal was read as a discount, so a correct total failed.
        case = scenario("normal")
        case.invoice_payload["invoice"].update(stated_other_charges_total="25000.00", stated_total="525000.00")
        validation = process(case)["validation"]
        self.assertEqual(validation["calculated_total"], "525000.00")
        self.assertIn("TOTAL_MATCH", {c["code"] for c in validation["checks"]})
        case = scenario("normal")
        case.invoice_payload["invoice"].update(stated_discount_total="25000.00", stated_total="525000.00")
        self.assertIn("TOTAL_MISMATCH", {c["code"] for c in process(case)["validation"]["checks"]})
        # Older payloads without the key keep their total, and the key takes plain decimals only.
        self.assertEqual(process(scenario("normal"))["validation"]["calculated_total"], "500000.00")
        payload = deepcopy(scenario("normal").invoice_payload)
        payload["invoice"]["stated_other_charges_total"] = "Rp25.000"
        with self.assertRaises(ContractError):
            validate_extraction(payload)

    def test_localized_money_evidence_can_match(self):
        case = scenario("normal")
        case.pages[0] += "\nTotal: Rp500.000,00"
        case.invoice_payload["source_evidence"]["stated_total"]["raw_value"] = "Rp500.000,00"
        self.assertEqual(process(case)["request_status"], "READY_FOR_REVIEW")

    def test_line_arithmetic_is_checked_separately(self):
        case = scenario("normal")
        case.invoice_payload["invoice"]["line_items"][0]["quantity"] = "3"
        case.pages[0] += "\nCorrected source quantity: 3"
        case.invoice_payload["source_evidence"]["line_items[0].quantity"]["raw_value"] = "3"
        codes = {c["code"] for c in process(case)["validation"]["checks"]}
        self.assertIn("LINE_TOTAL_MISMATCH", codes)

    def test_missing_line_operand_is_not_zero(self):
        case = scenario("normal")
        case.invoice_payload["invoice"]["line_items"][0]["quantity"] = None
        result = process(case)
        self.assertEqual(result["request_status"], "EXCEPTION")
        self.assertIn("INSUFFICIENT_CALCULATION_EVIDENCE", {c["code"] for c in result["validation"]["checks"]})

    def test_tolerance_is_explicit_and_invalid_tolerance_rejected(self):
        case = scenario("wrong_total")
        result = process(case, rules=Rules(tolerance=Decimal("10000.00")))
        self.assertEqual(result["request_status"], "READY_FOR_REVIEW")
        with self.assertRaises(ContractError):
            Rules(tolerance=Decimal("NaN"))

    def test_high_native_confidence_does_not_clear_exceptions(self):
        case = scenario("missing_bank")
        raw = case.raw_response("mistral")
        raw["pages"][0]["confidence_scores"] = {"average_page_confidence_score": 1.0}
        result = process_invoice(raw, MistralAdapter(), FixtureExtractor(case.invoice_payload),
                                 document_id="doc_demo_001", expected_pages=1, context=case.context)
        self.assertEqual(result["request_status"], "EXCEPTION")


class AdapterTests(unittest.TestCase):
    def test_mistral_out_of_order_pages_sorted(self):
        raw = scenario("five_pages").raw_response("mistral")
        raw["pages"].reverse()
        doc = MistralAdapter().normalize(raw, document_id="doc_demo_001", expected_pages=5)
        self.assertTrue(doc.complete)
        self.assertEqual([p.number for p in doc.pages], [1, 2, 3, 4, 5])

    def test_mistral_duplicate_or_out_of_range_pages_rejected(self):
        for index in (0, 5):
            with self.subTest(index=index):
                raw = scenario("five_pages").raw_response("mistral")
                raw["pages"][-1]["index"] = index
                with self.assertRaises(ProviderError):
                    MistralAdapter().normalize(raw, document_id="doc_demo_001", expected_pages=5)

    def test_ocrspace_failed_page_cannot_be_complete(self):
        raw = scenario("normal").raw_response("ocr_space")
        raw["ParsedResults"][0]["FileParseExitCode"] = -20
        with self.assertRaises(ProviderError):
            OCRSpaceAdapter().normalize(raw, document_id="doc_demo_001", expected_pages=1)

    def test_chunk_mapping_keeps_original_five_page_order(self):
        raw = scenario("five_pages").raw_response("ocr_space")
        one, two = deepcopy(raw), deepcopy(raw)
        one["ParsedResults"], two["ParsedResults"] = raw["ParsedResults"][:3], raw["ParsedResults"][3:]
        adapter = OCRSpaceAdapter()
        first = adapter.normalize(one, document_id="doc_demo_001", expected_pages=5, page_numbers=(1, 2, 3))
        second = adapter.normalize(two, document_id="doc_demo_001", expected_pages=5, page_numbers=(4, 5))
        merged = merge_chunks((second, first), 5)
        self.assertTrue(merged.complete)
        self.assertEqual([p.number for p in merged.pages], [1, 2, 3, 4, 5])
        with self.assertRaises(ProviderError):
            merge_chunks((first, first), 5)

    def test_string_false_is_not_treated_as_boolean(self):
        raw = scenario("normal").raw_response("ocr_space")
        raw["IsErroredOnProcessing"] = "false"
        with self.assertRaises(ProviderError):
            OCRSpaceAdapter().normalize(raw, document_id="doc_demo_001", expected_pages=1)


if __name__ == "__main__":
    unittest.main()
