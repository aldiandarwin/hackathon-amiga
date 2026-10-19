"""Run offline checks and save reproducible, explicitly scoped evidence."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amiga_ocr.cli import run_case
from amiga_ocr.fixtures import CASE_EXPECTATIONS


def main():
    started = perf_counter()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    matrix = []
    for name in CASE_EXPECTATIONS:
        for provider in ("ocr_space", "mistral"):
            case, response = run_case(name, provider)
            codes = {c["code"] for c in response["validation"]["checks"]}
            passed = (
                response["request_status"] == case.expected_status
                and set(case.required_codes) <= codes
                and response["review"]["can_approve"] == (case.expected_status == "READY_FOR_REVIEW")
            )
            matrix.append({"case": name, "provider": provider, "expected_status": case.expected_status,
                           "actual_status": response["request_status"], "result": "PASS" if passed else "FAIL",
                           "can_approve_in_local_context": response["review"]["can_approve"],
                           "checks": response["validation"]["checks"]})
            if name in ("normal", "missing_bank", "wrong_total", "five_pages"):
                (output / f"{name}-{provider}.json").write_text(
                    json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    success = result.wasSuccessful() and all(row["result"] == "PASS" for row in matrix)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "OFFLINE_SYNTHETIC_PIPELINE_AND_UNIT_TESTS",
        "live_provider_calls": 0, "live_ocr_accuracy_tested": False,
        "live_latency_targets_tested": False, "database_or_http_authorization_tested": False,
        "unit_tests": {"run": result.testsRun, "failures": len(result.failures),
                       "errors": len(result.errors), "skipped": len(result.skipped)},
        "scenario_runs": len(matrix), "scenario_passes": sum(row["result"] == "PASS" for row in matrix),
        "local_verification_elapsed_seconds": round(perf_counter() - started, 4),
        "result": "PASS" if success else "FAIL", "scenarios": matrix,
    }
    (output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Hasil verifikasi prototype AMIGA", "",
        f"Generated UTC: {report['generated_at_utc']}", "",
        f"Hasil: **{report['result']}**. Unit tests: **{result.testsRun}**, failures: {len(result.failures)}, errors: {len(result.errors)}.",
        f"Scenario runs: **{len(matrix)}**, passed: **{report['scenario_passes']}**.", "",
        "Semua input sintetis dan extraction memakai fixture. Tidak ada API call, billing, atau uji akurasi OCR nyata.",
        "Izin review diuji dengan trusted context lokal; database RLS, autentikasi HTTP, audit persistence, voucher, dan SLA belum diuji.", "",
        "| Case | Provider mock | Expected | Actual | Result |", "|---|---|---|---|---|",
    ]
    lines.extend(f"| {row['case']} | {row['provider']} | {row['expected_status']} | {row['actual_status']} | {row['result']} |" for row in matrix)
    lines.extend(["", "Detail checks tersedia pada [verification.json](verification.json).", ""])
    (output / "VERIFICATION.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved offline evidence: {output / 'VERIFICATION.md'}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
