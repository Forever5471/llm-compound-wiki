---
name: wiki-parse-docx
description: Use when capturing or preparing Microsoft Word .docx files for wiki ingest, including body text, headings, tables, and embedded-image notes.
---

# Wiki Parse DOCX

Goal: convert a `.docx` source into clean Markdown or UTF-8 text that can be captured under `raw/captures/` and then compiled into `wiki/`.

## Preferred Tool Order

1. If available, use a document parser that preserves structure, such as Docling, MarkItDown, Unstructured, or MinerU.
2. If no parser is installed, use `cwiki capture . <file.docx>`; the CLI has a built-in OOXML body-text extractor.
3. If the document has important tables, screenshots, comments, or tracked changes, tell the user extraction may be partial and recommend a richer parser before ingest.

## Workflow

1. Extract to Markdown or UTF-8 text.
2. Preserve source language; do not translate.
3. Keep document headings and table boundaries visible when possible.
4. Capture the extracted result with `cwiki capture`.
5. Process the generated ingest prompt with `wiki-ingest`.

## Quality Checks

- Confirm title, section headings, and key tables survived extraction.
- Flag embedded images that need `wiki-parse-image`.
- Cite the raw captured file path in all claim ledger rows.

