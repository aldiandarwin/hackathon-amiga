"""Local orchestration. Approval persistence and HTTP/auth are out of scope."""

from copy import deepcopy
from dataclasses import dataclass
from uuid import uuid4

from .contracts import Actor, Context, ContractError, InvoiceExtractor, ProviderError, Rules, validate_extraction
from .validation import check, review_permission, validate_invoice


@dataclass
class FixtureExtractor:
    """Returns supplied synthetic extraction; not an AI/OCR implementation."""
    payload: dict

    def extract(self, document):
        return deepcopy(self.payload)


def process_invoice(raw_response: dict, adapter, extractor: InvoiceExtractor, *,
                    document_id: str, expected_pages: int, context: Context,
                    actor: Actor | None = None, expected_version: int | None = None,
                    rules: Rules | None = None, page_numbers=None) -> dict:
    rules = rules or Rules()
    result = {
        "example_kind": "OFFLINE_SYNTHETIC_PROTOTYPE",
        "schema_version": "invoice-extraction.v1",
        "request_id": context.request_id, "client_id": context.client_id,
        "request_status": "PROCESSING", "invoice_version": context.invoice_version,
        "processing": {"run_id": str(uuid4()), "mode": "OFFLINE_MOCK", "live_provider_calls": 0,
                       "status": "PROCESSING", "measured_live_duration_ms": None, "billed_cost_usd": None},
        "invoice": None, "source_evidence": {},
        "voucher": {"status": "NOT_CREATED", "approved_version": None},
    }
    try:
        document = adapter.normalize(raw_response, document_id=document_id,
                                     expected_pages=expected_pages, page_numbers=page_numbers)
        result["processing"].update({
            "provider": document.provider, "model_or_engine": document.model,
            "expected_page_count": document.expected_pages, "returned_page_count": len(document.pages),
            "pages_complete": document.complete,
            "page_confidence": [{"page": p.number, "native_confidence": p.native_confidence} for p in document.pages],
            "extractor": "fixture", "prompt_version": None,
        })
        extraction = validate_extraction(extractor.extract(document))
        validation = validate_invoice(extraction, document, context, rules)
        result.update(extraction)
        result["validation"] = validation
        result["processing"]["status"] = "COMPLETED"
    except (ProviderError, ContractError) as error:
        result["processing"]["status"] = "FAILED"
        result["processing"]["error_code"] = "INVALID_PROVIDER_RESPONSE" if isinstance(error, ProviderError) else "INVALID_EXTRACTION_CONTRACT"
        result["validation"] = {"rules_version": rules.version, "calculated_subtotal": None,
                                "calculated_total": None, "total_difference": None,
                                "checks": [check("EXTRACTION_FAILED", "FAILED", str(error))]}
    blocked = any(item["blocking"] and item["status"] != "PASSED" for item in result["validation"]["checks"])
    result["request_status"] = "EXCEPTION" if blocked else "READY_FOR_REVIEW"
    allowed, reasons = review_permission(actor, context, result["request_status"], expected_version)
    result["review"] = {"required": True, "can_approve": allowed, "blocked_reasons": reasons,
                        "approved_by": None, "approved_version": None,
                        "permission_scope": "LOCAL_CONTEXT_CHECK_NOT_DATABASE_AUTHORIZATION"}
    return result
