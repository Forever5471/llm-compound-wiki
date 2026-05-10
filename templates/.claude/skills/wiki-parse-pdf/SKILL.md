---
name: wiki-parse-pdf
description: Use when capturing or preparing PDF files for wiki ingest, including born-digital PDFs, scanned PDFs, tables, figures, and layout-sensitive documents.
---

# Wiki Parse PDF

Goal: convert a PDF into readable Markdown or UTF-8 text while preserving enough structure for reliable wiki compilation.

## Preferred Tool Order

1. For complex PDFs, prefer open-source document parsers such as Docling, MinerU, Unstructured, Marker, or MarkItDown.
2. For simple born-digital PDFs, `cwiki capture` can use local `pdftotext` when installed.
3. For scanned PDFs or image-heavy pages, use OCR first, then capture the OCR output.

## Workflow

1. Determine PDF type: born-digital, scanned, mixed, or layout-heavy.
2. Extract text with structure-aware tooling when available.
3. For scanned pages, run OCR and keep page numbers or image references.
4. Capture the extracted Markdown/text with `cwiki capture`.
5. Process the generated ingest prompt with `wiki-ingest`.

## Quality Checks

- Verify page count and section coverage.
- Check tables, captions, footnotes, formulas, and multi-column reading order.
- Mark extraction uncertainty in the ingest summary if OCR or layout recovery was imperfect.

