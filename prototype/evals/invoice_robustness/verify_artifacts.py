"""Read-only fixture integrity/content checks plus optional local render/contact sheets."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evaluate import DATA, ROOT, load_cases
from amiga_ocr.validation import normalized_text, field_values


def verify():
    cases, manifest = load_cases()
    checked = []
    families = {}
    for case in cases:
        identifier, source, expected = case['case_id'], case['input'], case['expected_behavior']
        family = case['metadata']['family']
        assert families.setdefault(family, case['split']) == case['split'], 'Family leakage between splits'
        pdf = ROOT / source['pdf']
        reader = PdfReader(pdf)
        assert not reader.is_encrypted
        assert 1 <= len(reader.pages) == source['invoice_page_count'] <= 5
        assert pdf.stat().st_size <= 5_000_000
        assert len(expected['annotated_pages']) == len(reader.pages)
        texts = [normalized_text(page.extract_text() or '') for page in reader.pages]
        assert set(expected['source_evidence']) == set(dict(field_values(expected['invoice'])))
        verified_quotes = 0
        for field, entry in expected['source_evidence'].items():
            if entry is None:
                continue
            assert entry['document_id'] == source['document_id']
            assert 1 <= entry['page'] <= len(reader.pages)
            annotated = normalized_text(expected['annotated_pages'][entry['page'] - 1])
            quote = normalized_text(entry['raw_value'])
            assert re.search(rf'(?<!\w){re.escape(quote)}(?!\w)', annotated), (identifier, field, 'annotation')
            if source['source_kind'] == 'DIGITAL_TEXT':
                assert re.search(rf'(?<!\w){re.escape(quote)}(?!\w)', texts[entry['page'] - 1]), (identifier, field, 'PDF text')
                verified_quotes += 1
        if source['source_kind'] == 'RASTER_ONLY':
            assert all(not text for text in texts), 'Raster fixture unexpectedly contains answer text'
            assert all(list(page.images) for page in reader.pages)
        checked.append({'case_id': identifier, 'pages': len(reader.pages), 'bytes': pdf.stat().st_size,
                        'source_kind': source['source_kind'], 'embedded_quotes_verified': verified_quotes})
    pack = ROOT / 'output/pdf/invoice-robustness-review-v1.pdf'
    assert sha256(pack.read_bytes()).hexdigest() == manifest['pack_sha256']
    assert len(PdfReader(pack).pages) == 1 + sum(c['pages'] for c in checked)
    return {'dataset_sha256': manifest['dataset_sha256'], 'cases': checked,
            'case_count': len(checked), 'invoice_pages': sum(c['pages'] for c in checked),
            'review_pack_pages': len(PdfReader(pack).pages), 'structural_checks': 'PASS',
            'holdout_quality_evaluation': 'NOT_RUN', 'visual_review': 'SEPARATE_MANUAL_STEP'}


def render(renderer):
    from PIL import Image, ImageDraw
    directory = ROOT / 'tmp/pdfs/robustness-v1'
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(renderer), '-r', '105', '-png', str(ROOT / 'output/pdf/invoice-robustness-review-v1.pdf'),
                    str(directory / 'page')], check=True, timeout=90)
    pages = sorted(directory.glob('page-*.png'), key=lambda p: int(p.stem.split('-')[-1]))
    assert len(pages) == 19
    sheets = []
    for start in range(0, len(pages), 6):
        sheet = Image.new('RGB', (820, 1782), '#dce5e7')
        draw = ImageDraw.Draw(sheet)
        for offset, path in enumerate(pages[start:start + 6]):
            with Image.open(path) as page:
                page.thumbnail((390, 554))
                x, y = 15 + (offset % 2) * 405, 22 + (offset // 2) * 590
                sheet.paste(page, (x, y))
                draw.text((x, y - 15), path.stem, fill='#173c45')
        target = directory / f'contact-{start // 6 + 1}.png'
        sheet.save(target)
        sheets.append(target.relative_to(ROOT).as_posix())
    return {'rendered_pages': len(pages), 'contact_sheets': sheets, 'renderer': 'Poppler pdftoppm 105 DPI'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdftoppm', type=Path)
    args = parser.parse_args()
    report = verify()
    if args.pdftoppm:
        report['render'] = render(args.pdftoppm)
    target = ROOT / 'output/evaluation/robustness-v1/artifact-check.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
