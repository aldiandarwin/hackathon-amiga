"""Reader-executable offline demo."""

import argparse
import json
from pathlib import Path

from .adapters import MistralAdapter, OCRSpaceAdapter
from .fixtures import CASE_EXPECTATIONS, scenario
from .pipeline import FixtureExtractor, process_invoice


def run_case(name, provider):
    case = scenario(name)
    result = process_invoice(
        case.raw_response(provider), OCRSpaceAdapter() if provider == "ocr_space" else MistralAdapter(),
        FixtureExtractor(case.invoice_payload), document_id="doc_demo_001", expected_pages=case.expected_pages,
        context=case.context, actor=case.actor, expected_version=case.context.invoice_version,
    )
    return case, result


def main(argv=None):
    parser = argparse.ArgumentParser(description="AMIGA offline mock demo; no API key or provider calls.")
    parser.add_argument("--case", choices=CASE_EXPECTATIONS, default="normal")
    parser.add_argument("--provider", choices=("ocr_space", "mistral"), default="ocr_space")
    parser.add_argument("--output", type=Path, help="Write response JSON to a local file.")
    args = parser.parse_args(argv)
    _, result = run_case(args.case, args.provider)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Offline result written to {args.output.resolve()}")
    else:
        print(text)
    return 0
