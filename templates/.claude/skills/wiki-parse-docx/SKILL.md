---
name: wiki-parse-docx
description: Use when capturing or preparing Microsoft Word .docx files for wiki ingest, including body text, headings, tables, and embedded-image notes.
---

# Wiki Parse DOCX

Goal: convert a `.docx` source into clean Markdown or UTF-8 text that can be captured under `raw/captures/` and then compiled into `wiki/`.

## Built-In Parser

Use the repository's built-in parser first:

```bash
cwiki capture . <file.docx> --title "<title>"
```

The CLI reads the `.docx` OOXML package directly and extracts body text, including paragraphs inside tables. It does not require external GitHub projects.

If the document has important embedded images, comments, tracked changes, or complex layout, explicitly mark those as extraction limits and route embedded images through `wiki-parse-image`.

## Workflow

1. Run `cwiki capture` on the `.docx`.
2. Preserve source language; do not translate.
3. Keep document headings and table boundaries visible when possible.
4. Capture the extracted result with `cwiki capture`.
5. Process the generated ingest prompt with `wiki-ingest`.

## Quality Checks

- Confirm title, section headings, and key tables survived extraction.
- Flag embedded images that need `wiki-parse-image`.
- Cite the raw captured file path in all claim ledger rows.
