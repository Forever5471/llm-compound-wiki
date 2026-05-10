---
name: wiki-parse-pdf
description: Use when capturing or preparing PDF files for wiki ingest, including born-digital PDFs, scanned PDFs, tables, figures, and layout-sensitive documents.
---

# Wiki Parse PDF

Goal: convert a PDF into readable Markdown or UTF-8 text while preserving enough structure for reliable wiki compilation.

## Built-In Parser

Use the repository's built-in path first:

```bash
cwiki capture . <file.pdf> --title "<title>"
```

For born-digital PDFs, the CLI uses the local `pdftotext` command when available. This does not call GitHub projects or remote parsers.

For scanned PDFs or image-heavy pages, use the built-in `wiki-parse-image` workflow page by page: inspect images with available vision/OCR capability, write extracted text and visual notes, then capture that text.

This project does not automatically search GitHub or integrate external parser projects. If built-in PDF extraction or OCR is not good enough, tell the user to convert the PDF to Markdown or UTF-8 text with a tool of their choice, then capture that converted file.

## Workflow

1. Determine PDF type: born-digital, scanned, mixed, or layout-heavy.
2. Extract text with `cwiki capture` when the PDF has selectable text.
3. For scanned pages, use `wiki-parse-image` and keep page numbers or image references.
4. Capture the extracted Markdown/text with `cwiki capture`.
5. Process the generated ingest prompt with `wiki-ingest`.

## Quality Checks

- Verify page count and section coverage.
- Check tables, captions, footnotes, formulas, and multi-column reading order.
- Mark extraction uncertainty in the ingest summary if OCR or layout recovery was imperfect.
