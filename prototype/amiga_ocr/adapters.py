"""Normalize saved provider JSON; this module does not perform HTTP requests."""

from copy import deepcopy

from .contracts import OCRDocument, OCRPage, ProviderError


def _page_mapping(expected_pages: int, page_numbers: tuple[int, ...] | None):
    if type(expected_pages) is not int or expected_pages < 1:
        raise ProviderError("Expected page count must be positive.")
    mapping = page_numbers if page_numbers is not None else tuple(range(1, expected_pages + 1))
    if (not mapping or any(type(n) is not int or n < 1 for n in mapping)
            or len(set(mapping)) != len(mapping)):
        raise ProviderError("Invalid original page mapping.")
    return mapping


def _document(document_id, provider, model, pages, expected_pages, raw, provider_ok):
    pages = tuple(sorted(pages, key=lambda p: p.number))
    if len({p.number for p in pages}) != len(pages):
        raise ProviderError("Duplicate page numbers in provider response.")
    complete = (
        provider_ok and len(pages) == expected_pages
        and {p.number for p in pages} == set(range(1, expected_pages + 1))
        and all(p.successful and p.text.strip() for p in pages)
    )
    if not pages or not any(p.successful and p.text.strip() for p in pages):
        raise ProviderError("Provider returned no readable pages.")
    return OCRDocument(document_id, provider, model, pages, expected_pages, complete, deepcopy(raw))


class OCRSpaceAdapter:
    def normalize(self, raw: dict, *, document_id: str, expected_pages: int,
                  model: str = "2", page_numbers: tuple[int, ...] | None = None) -> OCRDocument:
        mapping = _page_mapping(expected_pages, page_numbers)
        if not isinstance(raw, dict) or type(raw.get("IsErroredOnProcessing")) is not bool:
            raise ProviderError("Malformed OCR.space processing status.")
        results = raw.get("ParsedResults")
        if not isinstance(results, list) or len(results) > len(mapping):
            raise ProviderError("Malformed OCR.space pages.")
        pages = []
        for index, result in enumerate(results):
            if not isinstance(result, dict):
                raise ProviderError("Malformed OCR.space page.")
            text = result.get("ParsedText")
            if text is not None and not isinstance(text, str):
                raise ProviderError("ParsedText must be text or null.")
            pages.append(OCRPage(mapping[index], text or "", str(result.get("FileParseExitCode")) == "1"))
        ok = str(raw.get("OCRExitCode")) == "1" and not raw["IsErroredOnProcessing"]
        return _document(document_id, "ocr_space", model, pages, expected_pages, raw, ok)


class MistralAdapter:
    def normalize(self, raw: dict, *, document_id: str, expected_pages: int,
                  model: str = "mistral-ocr-4-1", page_numbers: tuple[int, ...] | None = None) -> OCRDocument:
        mapping = _page_mapping(expected_pages, page_numbers)
        if not isinstance(raw, dict) or not isinstance(raw.get("pages"), list):
            raise ProviderError("Malformed Mistral pages.")
        pages = []
        for page in raw["pages"]:
            if not isinstance(page, dict):
                raise ProviderError("Malformed Mistral page.")
            index, markdown = page.get("index"), page.get("markdown")
            if type(index) is not int or index < 0 or index >= len(mapping):
                raise ProviderError("Invalid Mistral page index.")
            if not isinstance(markdown, str):
                raise ProviderError("Mistral markdown must be text.")
            pages.append(OCRPage(mapping[index], markdown, True, deepcopy(page.get("confidence_scores"))))
        return _document(document_id, "mistral", str(raw.get("model") or model), pages, expected_pages, raw, True)


def merge_chunks(chunks: tuple[OCRDocument, ...], expected_pages: int) -> OCRDocument:
    if not chunks:
        raise ProviderError("No OCR chunks supplied.")
    first = chunks[0]
    if any((c.document_id, c.provider, c.model) != (first.document_id, first.provider, first.model) for c in chunks):
        raise ProviderError("Chunks must belong to the same document and provider/model.")
    pages = tuple(page for chunk in chunks for page in chunk.pages)
    raw = {"chunks": [deepcopy(chunk.raw_response) for chunk in chunks]}
    # Chunk completeness is relative to its original page mapping. Global completeness
    # is checked here from all mapped original pages and each page's processing status.
    provider_ok = all(
        str(c.raw_response.get("OCRExitCode")) == "1" and not c.raw_response.get("IsErroredOnProcessing", True)
        if c.provider == "ocr_space" else True
        for c in chunks
    )
    return _document(first.document_id, first.provider, first.model, pages, expected_pages, raw, provider_ok)
