"""Provider-neutral types and strict extraction boundary, using stdlib only."""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import re
from typing import Any, Protocol


class ContractError(ValueError):
    pass


class ProviderError(ValueError):
    pass


@dataclass(frozen=True)
class OCRPage:
    number: int
    text: str
    successful: bool = True
    native_confidence: Any = None


@dataclass(frozen=True)
class OCRDocument:
    document_id: str
    provider: str
    model: str
    pages: tuple[OCRPage, ...]
    expected_pages: int
    complete: bool
    raw_response: dict


class InvoiceExtractor(Protocol):
    def extract(self, document: OCRDocument) -> dict:
        """Return invoice and source_evidence only; never workflow decisions."""
        ...


@dataclass(frozen=True)
class Rules:
    version: str = "demo-rules.v1"
    tolerance: Decimal = Decimal("0.00")
    allowed_currencies: tuple[str, ...] = ("IDR",)
    required_fields: tuple[str, ...] = (
        "vendor_name", "invoice_number", "invoice_date", "currency",
        "stated_total", "payment.account_number",
    )

    def __post_init__(self):
        if not self.tolerance.is_finite() or self.tolerance < 0:
            raise ContractError("Tolerance must be a nonnegative finite Decimal.")


@dataclass(frozen=True)
class Context:
    client_id: str
    request_id: str
    uploaded_by: str
    invoice_version: int = 1
    vendor_directory: dict[str, str] = field(default_factory=dict)
    bank_accounts: dict[str, tuple[str, ...]] = field(default_factory=dict)
    bank_master_loaded: bool = False
    previous_invoices: tuple[dict, ...] = ()
    history_loaded: bool = False
    vendor_npwp: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Actor:
    user_id: str
    roles: tuple[str, ...]
    client_ids: tuple[str, ...]


def decimal_value(value: Any) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        raise ContractError("Numeric values must be plain decimal strings.")
    if len(value.replace("-", "").replace(".", "")) > 40:
        raise ContractError("Prototype numeric values are limited to 40 digits.")
    return Decimal(value)


def _keys(obj: Any, required: set[str], location: str):
    if not isinstance(obj, dict) or set(obj) != required:
        raise ContractError(f"{location}: unexpected or missing fields.")


# Schema v2 (14 Okt 2026): tax identity read from the document so nobody retypes it. Saved samples and stored
# snapshots are v1 and omit these keys, so they stay optional here.
METADATA_FIELDS = ("vendor_npwp", "buyer_name", "buyer_npwp", "po_number", "faktur_number", "faktur_date")
# Schema v3 (15 Okt 2026): charges printed below the subtotal (biaya admin, layanan, ongkir, tools). A model once read
# such a charge as a discount, so the total no longer matched. Optional for the same reason as the v2 keys.
OPTIONAL_MONEY_FIELDS = ("stated_other_charges_total",)


def validate_extraction(payload: Any) -> dict:
    """Reject malformed model output rather than coercing guessed values."""
    _keys(payload, {"invoice", "source_evidence"}, "extraction")
    invoice = payload["invoice"]
    string_fields = {
        "vendor_name", "invoice_number", "invoice_date", "due_date", "currency",
    }
    money_fields = {
        "stated_subtotal", "stated_discount_total", "stated_tax_total", "stated_total",
    }
    base = string_fields | money_fields | {"vendor_id", "line_items", "payment"}
    if not isinstance(invoice, dict) or not base <= set(invoice) <= base | set(METADATA_FIELDS) | set(OPTIONAL_MONEY_FIELDS):
        raise ContractError("invoice: unexpected or missing fields.")
    if invoice["vendor_id"] is not None:
        raise ContractError("vendor_id must be resolved by trusted backend context.")
    for key in string_fields | (set(METADATA_FIELDS) & set(invoice)):
        value = invoice[key]
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ContractError(f"{key}: use nonempty text or null.")
    for key in ("invoice_date", "due_date", "faktur_date"):
        value = invoice.get(key)
        if value is not None:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError()
                date.fromisoformat(value)
            except ValueError:
                raise ContractError(f"{key}: expected an unambiguous ISO date.") from None
    if invoice["currency"] is not None and not re.fullmatch(r"[A-Z]{3}", invoice["currency"]):
        raise ContractError("currency: expected a three-letter uppercase code.")
    for key in money_fields | (set(OPTIONAL_MONEY_FIELDS) & set(invoice)):
        if invoice[key] is not None:
            decimal_value(invoice[key])
    _keys(invoice["payment"], {"bank_name", "account_holder", "account_number"}, "payment")
    for key, value in invoice["payment"].items():
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ContractError(f"payment.{key}: expected text or null.")
    items = invoice["line_items"]
    if not isinstance(items, list) or len(items) > 1000:
        raise ContractError("line_items: expected an array of at most 1000 items.")
    for index, item in enumerate(items):
        _keys(item, {"line_number", "description", "quantity", "unit_price", "stated_line_total"}, "line_item")
        if type(item["line_number"]) is not int or item["line_number"] != index + 1:
            raise ContractError("Line numbers must be contiguous and in source order.")
        description = item["description"]
        if description is not None and (not isinstance(description, str) or not description.strip()):
            raise ContractError("Item description: expected text or null.")
        for key in ("quantity", "unit_price", "stated_line_total"):
            if item[key] is not None:
                decimal_value(item[key])
    evidence = payload["source_evidence"]
    if not isinstance(evidence, dict):
        raise ContractError("source_evidence must be an object.")
    for entry in evidence.values():
        if entry is None:
            continue
        _keys(entry, {"document_id", "page", "raw_value", "bbox"}, "evidence")
        if not isinstance(entry["document_id"], str) or not entry["document_id"]:
            raise ContractError("Evidence requires a document ID.")
        if type(entry["page"]) is not int or entry["page"] < 1:
            raise ContractError("Evidence page numbers start at 1.")
        if not isinstance(entry["raw_value"], str) or not entry["raw_value"].strip():
            raise ContractError("Evidence quotes must not be empty.")
        if entry["bbox"] is not None:
            raise ContractError("The offline prototype supports null bounding boxes only.")
    return deepcopy(payload)
