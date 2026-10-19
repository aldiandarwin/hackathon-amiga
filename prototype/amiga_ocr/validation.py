"""Deterministic demonstration rules; Finance still owns production policy."""

from decimal import Decimal, localcontext
import re
import unicodedata

from .contracts import Actor, Context, OCRDocument, Rules, decimal_value


def normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def identity(value: str) -> str:
    return normalized_text(value).casefold()


# Copied character for character from the document; a near match is a misread, not a format difference.
IDENTIFIERS = ("invoice_number", "payment.account_number", "vendor_npwp", "buyer_npwp", "po_number", "faktur_number")


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def check(code, status, message, *, field=None, blocking=None):
    return {
        "code": code, "status": status,
        "blocking": status != "PASSED" if blocking is None else blocking,
        "field": field, "message": message,
    }


def field_values(invoice):
    for key, value in invoice.items():
        if key == "vendor_id":
            continue
        if key == "payment":
            for subkey, subvalue in value.items():
                yield f"payment.{subkey}", subvalue
        elif key == "line_items":
            for index, item in enumerate(value):
                for subkey, subvalue in item.items():
                    if subkey != "line_number":
                        yield f"line_items[{index}].{subkey}", subvalue
        else:
            yield key, value


def _numeric_quote(raw: str) -> Decimal | None:
    matches = re.findall(r"-?\d[\d.,]*", raw)
    if len(matches) != 1:
        return None
    token = matches[0]
    if "," in token:
        if not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:\.\d{3})+),\d{1,6}", token):
            return None
        token = token.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3}){2,}", token):
        # Two or more dots, each followed by exactly three digits: only thousands grouping reads this way (Rp 66.600.000).
        token = token.replace(".", "")
    elif token.count(".") > 1 or re.fullmatch(r"-?\d{1,3}\.\d{3}", token):
        # 1.234 might be a decimal or a thousands-grouped value; do not guess.
        return None
    return decimal_value(token)


def _evidence_checks(invoice, evidence, document):
    checks = []
    pages = {p.number: p for p in document.pages}
    for path, value in field_values(invoice):
        if value is None:
            continue
        entry = evidence.get(path)
        valid = isinstance(entry, dict) and entry["document_id"] == document.document_id
        page = pages.get(entry["page"]) if valid else None
        valid = valid and page is not None and page.successful
        if valid:
            quote = normalized_text(entry["raw_value"])
            valid = re.search(rf"(?<!\w){re.escape(quote)}(?!\w)", normalized_text(page.text)) is not None
        if not valid:
            checks.append(check("SOURCE_EVIDENCE_INVALID", "FAILED", "Bukti sumber tidak tersedia pada halaman yang ditunjuk.", field=path))
            continue
        numeric = path.startswith("stated_") or path.endswith((".quantity", ".unit_price", ".stated_line_total"))
        if numeric:
            quoted = _numeric_quote(quote)
            if quoted is None:
                checks.append(check("AMBIGUOUS_VALUE", "FAILED", "Angka dalam bukti sumber belum dapat dinormalisasi secara pasti.", field=path))
            elif quoted != decimal_value(value):
                checks.append(check("SOURCE_VALUE_MISMATCH", "FAILED", "Nilai ekstraksi berbeda dari bukti sumber.", field=path))
        elif path in ("invoice_date", "due_date", "faktur_date"):
            if not re.search(rf"(?<!\d){re.escape(value)}(?!\d)", quote):
                checks.append(check("AMBIGUOUS_VALUE", "FAILED", "Prototype memerlukan bukti tanggal ISO yang tidak ambigu.", field=path))
        elif path in IDENTIFIERS and normalized_text(value) != quote:
            checks.append(check("SOURCE_VALUE_MISMATCH", "FAILED", "Identifier berbeda dari nilai sumber yang dikutip.", field=path))
        elif normalized_text(value) not in quote:
            checks.append(check("SOURCE_VALUE_MISMATCH", "FAILED", "Nilai ekstraksi tidak didukung kutipan sumber.", field=path))
    if not checks:
        checks.append(check("SOURCE_EVIDENCE_MATCH", "PASSED", "Nilai terisi mempunyai kutipan sumber yang sesuai."))
    return checks


def validate_invoice(extraction: dict, document: OCRDocument, context: Context, rules: Rules, *,
                     declared_zero=frozenset()):
    unknown = set(declared_zero) - {"stated_discount_total", "stated_tax_total"}
    if unknown:
        raise ValueError(f"Unsupported declared-zero field: {sorted(unknown)}")
    invoice = extraction["invoice"]
    checks = [check("OCR_COMPLETE" if document.complete else "OCR_INCOMPLETE",
                    "PASSED" if document.complete else "FAILED", "Pemeriksaan kelengkapan halaman OCR.")]
    values = dict(field_values(invoice))
    for path in rules.required_fields:
        if path not in values:
            raise ValueError(f"Unknown configured required field: {path}")
        if values[path] is None:
            checks.append(check("MISSING_EVIDENCE", "FAILED", "Field wajib belum tersedia.", field=path))
    checks.extend(_evidence_checks(invoice, extraction["source_evidence"], document))
    if invoice["currency"] is not None and invoice["currency"] not in rules.allowed_currencies:
        checks.append(check("UNSUPPORTED_CURRENCY", "FAILED", "Mata uang di luar cakupan konfigurasi demo.", field="currency"))

    calculated_subtotal = calculated_total = difference = None
    items = invoice["line_items"]
    with localcontext() as precision:
        # At most 40-digit operands and 1000 items: 200 digits also retain sums
        # containing both very large integer products and tiny decimal products.
        precision.prec = 200
        if not items:
            checks.append(check("MISSING_EVIDENCE", "FAILED", "Line items belum tersedia.", field="line_items"))
        for index, item in enumerate(items):
            operands = (item["quantity"], item["unit_price"], item["stated_line_total"])
            if any(value is None for value in operands):
                checks.append(check("INSUFFICIENT_CALCULATION_EVIDENCE", "NOT_CHECKED", "Angka baris belum lengkap.", field=f"line_items[{index}]"))
            else:
                delta = decimal_value(operands[0]) * decimal_value(operands[1]) - decimal_value(operands[2])
                checks.append(check("LINE_TOTAL_MATCH" if abs(delta) <= rules.tolerance else "LINE_TOTAL_MISMATCH",
                                    "PASSED" if abs(delta) <= rules.tolerance else "FAILED",
                                    "Pemeriksaan quantity x unit price terhadap total baris.", field=f"line_items[{index}]"))
        if items and all(item["stated_line_total"] is not None for item in items):
            calculated_subtotal = sum((decimal_value(item["stated_line_total"]) for item in items), Decimal(0))
        if calculated_subtotal is None or invoice["stated_subtotal"] is None:
            checks.append(check("INSUFFICIENT_CALCULATION_EVIDENCE", "NOT_CHECKED", "Subtotal tidak dapat diperiksa."))
        else:
            delta = calculated_subtotal - decimal_value(invoice["stated_subtotal"])
            checks.append(check("SUBTOTAL_MATCH" if abs(delta) <= rules.tolerance else "SUBTOTAL_MISMATCH",
                                "PASSED" if abs(delta) <= rules.tolerance else "FAILED", "Pemeriksaan jumlah total baris."))
        keys = ("stated_discount_total", "stated_tax_total", "stated_total")
        for key in keys:
            if invoice[key] is None and key in declared_zero:
                checks.append(check("DECLARED_ZERO", "PASSED",
                                    "Nilai kosong dihitung 0 atas pernyataan pengguna, bukan hasil baca dokumen.", field=key))
        totals = ["0" if invoice[k] is None and k in declared_zero else invoice[k] for k in keys]
        # Unlike discount and tax, an empty other-charges field counts as 0: most invoices print no such charge,
        # and snapshots older than schema v3 do not have the key at all.
        other = invoice.get("stated_other_charges_total")
        other = decimal_value(other) if other is not None else Decimal(0)
        # 16 Okt 2026, Aldian: an invoice without a discount line is the usual case, not missing data. An empty discount
        # counts as none only when the printed numbers then close the total; with a gap, an unread discount could be
        # the cause, so the total stays unchecked.
        no_discount = (totals[0] is None and calculated_subtotal is not None and None not in totals[1:]
                       and abs(calculated_subtotal + other + decimal_value(totals[1]) - decimal_value(totals[2]))
                       <= rules.tolerance)
        if no_discount:
            totals[0] = "0"
        if calculated_subtotal is None or any(value is None for value in totals):
            checks.append(check("INSUFFICIENT_CALCULATION_EVIDENCE", "NOT_CHECKED", "Penyesuaian/total belum lengkap; null tidak diasumsikan nol."))
        else:
            calculated_total = calculated_subtotal - decimal_value(totals[0]) + other + decimal_value(totals[1])
            difference = calculated_total - decimal_value(totals[2])
            checks.append(check("TOTAL_MATCH" if abs(difference) <= rules.tolerance else "TOTAL_MISMATCH",
                                "PASSED" if abs(difference) <= rules.tolerance else "FAILED",
                                "Total cocok tanpa diskon; invoice tidak mencantumkan diskon." if no_discount
                                else "Pemeriksaan total dengan aturan demo."))

    vendor_id = context.vendor_directory.get(identity(invoice["vendor_name"])) if invoice["vendor_name"] else None
    invoice["vendor_id"] = vendor_id
    if not vendor_id or not context.history_loaded or invoice["invoice_number"] is None:
        checks.append(check("DUPLICATE_CHECK", "NOT_CHECKED", "Master vendor/riwayat/nomor invoice belum siap."))
    else:
        matches = [record for record in context.previous_invoices if
                   record["client_id"] == context.client_id and record["vendor_id"] == vendor_id
                   and identity(record["invoice_number"]) == identity(invoice["invoice_number"])
                   and record["request_id"] != context.request_id and record.get("active", True)]
        checks.append(check("POSSIBLE_DUPLICATE" if matches else "DUPLICATE_CHECK",
                            "FAILED" if matches else "PASSED", "Pemeriksaan kandidat duplikasi dalam scope klien."))
    account = invoice["payment"]["account_number"]
    if not vendor_id or not context.bank_master_loaded or account is None:
        checks.append(check("BANK_UNVERIFIED", "NOT_CHECKED", "Verifikasi rekening belum dapat dilakukan."))
    else:
        verified = account in context.bank_accounts.get(vendor_id, ())
        checks.append(check("BANK_VERIFIED" if verified else "BANK_MISMATCH",
                            "PASSED" if verified else "FAILED", "Pencocokan dengan master demo yang sudah diverifikasi."))
    # Like the bank account, a printed NPWP that differs from the vendor master suggests the wrong payee.
    master_npwp = context.vendor_npwp.get(vendor_id) if vendor_id else None
    if invoice.get("vendor_npwp") and master_npwp:
        same = digits(invoice["vendor_npwp"]) == digits(master_npwp)
        checks.append(check("NPWP_MATCH" if same else "NPWP_MISMATCH", "PASSED" if same else "FAILED",
                            "NPWP vendor dicocokkan dengan master vendor.", field="vendor_npwp"))
    return {
        "rules_version": rules.version,
        "calculated_subtotal": format(calculated_subtotal, "f") if calculated_subtotal is not None else None,
        "calculated_total": format(calculated_total, "f") if calculated_total is not None else None,
        "total_difference": format(difference, "f") if difference is not None else None,
        "checks": checks,
    }


def review_permission(actor: Actor | None, context: Context, status: str, expected_version: int | None):
    reasons = []
    if actor is None:
        reasons.append("UNAUTHENTICATED")
    else:
        if "FINANCE_REVIEWER" not in actor.roles or "SYSTEM_ADMIN" in actor.roles:
            reasons.append("ROLE_NOT_ALLOWED")
        if context.client_id not in actor.client_ids:
            reasons.append("CLIENT_NOT_ASSIGNED")
        if actor.user_id == context.uploaded_by:
            reasons.append("SELF_APPROVAL_FORBIDDEN")
    if status != "READY_FOR_REVIEW":
        reasons.append("UNRESOLVED_EXCEPTION")
    if expected_version != context.invoice_version:
        reasons.append("VERSION_CONFLICT")
    return not reasons, reasons
