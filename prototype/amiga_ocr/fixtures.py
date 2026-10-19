"""Synthetic invoices and trusted demo context, never real client data."""

from copy import deepcopy
from dataclasses import dataclass, replace

from .contracts import Actor, Context
from .validation import field_values, identity


@dataclass
class Scenario:
    name: str
    invoice_payload: dict
    pages: list[str]
    expected_pages: int
    context: Context
    actor: Actor
    expected_status: str
    required_codes: tuple[str, ...]
    provider_failure: bool = False

    def raw_response(self, provider: str):
        if provider == "ocr_space":
            return {
                "ParsedResults": [] if self.provider_failure else [
                    {"ParsedText": text, "FileParseExitCode": 1, "TextOverlay": None,
                     "ErrorMessage": None, "ErrorDetails": None} for text in self.pages
                ],
                "OCRExitCode": 3 if self.provider_failure else (1 if len(self.pages) == self.expected_pages else 2),
                "IsErroredOnProcessing": self.provider_failure,
                "ErrorMessage": "Synthetic provider failure" if self.provider_failure else None,
            }
        if provider == "mistral":
            return {
                "pages": [] if self.provider_failure else [
                    {"index": index, "markdown": text, "confidence_scores": None}
                    for index, text in enumerate(self.pages)
                ],
                "model": "mistral-ocr-4-1",
                "usage_info": {"pages_processed": 0 if self.provider_failure else len(self.pages)},
            }
        raise ValueError("Unknown provider.")


def _invoice():
    return {
        "vendor_id": None, "vendor_name": "PT Contoh Demo", "invoice_number": "INV-DEMO-001",
        "invoice_date": "2026-10-12", "due_date": None, "currency": "IDR",
        "line_items": [
            {"line_number": 1, "description": "Barang contoh A", "quantity": "2",
             "unit_price": "150000.00", "stated_line_total": "300000.00"},
            {"line_number": 2, "description": "Barang contoh B", "quantity": "1",
             "unit_price": "125000.00", "stated_line_total": "125000.00"},
            {"line_number": 3, "description": "Barang contoh C", "quantity": "3",
             "unit_price": "25000.00", "stated_line_total": "75000.00"},
        ],
        "stated_subtotal": "500000.00", "stated_discount_total": "0.00",
        "stated_tax_total": "0.00", "stated_total": "500000.00",
        "payment": {"bank_name": "Bank Contoh", "account_holder": "PT Contoh Demo", "account_number": "00123456"},
    }


CASE_EXPECTATIONS = {
    "normal": ("READY_FOR_REVIEW", ("TOTAL_MATCH", "BANK_VERIFIED")),
    "missing_bank": ("EXCEPTION", ("MISSING_EVIDENCE",)),
    "wrong_total": ("EXCEPTION", ("TOTAL_MISMATCH",)),
    "duplicate": ("EXCEPTION", ("POSSIBLE_DUPLICATE",)),
    "different_client": ("READY_FOR_REVIEW", ("DUPLICATE_CHECK",)),
    "partial_ocr": ("EXCEPTION", ("OCR_INCOMPLETE",)),
    "failed_ocr": ("EXCEPTION", ("EXTRACTION_FAILED",)),
    "unsupported_value": ("EXCEPTION", ("SOURCE_VALUE_MISMATCH",)),
    "forged_quote": ("EXCEPTION", ("SOURCE_EVIDENCE_INVALID",)),
    "bank_mismatch": ("EXCEPTION", ("BANK_MISMATCH",)),
    "unknown_bank_master": ("EXCEPTION", ("BANK_UNVERIFIED",)),
    "unknown_history": ("EXCEPTION", ("DUPLICATE_CHECK",)),
    # 16 Okt 2026: no discount line closes the total, so nothing is missing; a gap could be an unread discount.
    "missing_discount": ("READY_FOR_REVIEW", ("TOTAL_MATCH",)),
    "missing_discount_gap": ("EXCEPTION", ("INSUFFICIENT_CALCULATION_EVIDENCE",)),
    "five_pages": ("READY_FOR_REVIEW", ("OCR_COMPLETE", "TOTAL_MATCH")),
}


def scenario(name: str) -> Scenario:
    if name not in CASE_EXPECTATIONS:
        raise ValueError(f"Unknown case: {name}")
    invoice = _invoice()
    context = Context(
        client_id="client_demo_a", request_id=f"req_demo_{name}", uploaded_by="user_pic",
        vendor_directory={identity("PT Contoh Demo"): "vendor_demo_001"},
        bank_accounts={"vendor_demo_001": ("00123456",)}, bank_master_loaded=True,
        history_loaded=True,
    )
    if name == "missing_bank":
        invoice["payment"]["account_number"] = None
    if name == "wrong_total":
        invoice["stated_total"] = "510000.00"
    if name == "bank_mismatch":
        invoice["payment"]["account_number"] = "00123457"
    if name in ("missing_discount", "missing_discount_gap"):
        invoice["stated_discount_total"] = None
    if name == "missing_discount_gap":
        invoice["stated_total"] = "490000.00"
    if name in ("duplicate", "different_client"):
        context = replace(context, previous_invoices=({
            "client_id": "client_demo_a" if name == "duplicate" else "client_demo_b",
            "vendor_id": "vendor_demo_001", "invoice_number": " inv-demo-001 ",
            "request_id": "req_previous", "active": True,
        },))
    if name == "unknown_bank_master":
        context = replace(context, bank_master_loaded=False, bank_accounts={})
    if name == "unknown_history":
        context = replace(context, history_loaded=False)

    page_count = 5 if name == "five_pages" else 1
    lines = [[f"SYNTHETIC DEMO INVOICE - PAGE {i + 1}"] for i in range(page_count)]
    evidence = {}
    for path, value in field_values(invoice):
        if value is None:
            evidence[path] = None
            continue
        page = 1
        if page_count == 5:
            if path.startswith("line_items["):
                page = int(path.split("[")[1].split("]")[0]) + 2
            elif path.startswith(("stated_", "payment.")):
                page = 5
        lines[page - 1].append(f"{path}: {value}")
        evidence[path] = {"document_id": "doc_demo_001", "page": page, "raw_value": value, "bbox": None}
    payload = {"invoice": deepcopy(invoice), "source_evidence": evidence}
    if name == "unsupported_value":
        payload["invoice"]["stated_total"] = "600000.00"
    if name == "forged_quote":
        payload["source_evidence"]["payment.account_number"]["raw_value"] = "99999999"
    expected_status, codes = CASE_EXPECTATIONS[name]
    return Scenario(
        name, payload, ["\n".join(page) for page in lines],
        2 if name == "partial_ocr" else page_count, context,
        Actor("user_finance", ("FINANCE_REVIEWER",), ("client_demo_a",)),
        expected_status, codes, name == "failed_ocr",
    )
