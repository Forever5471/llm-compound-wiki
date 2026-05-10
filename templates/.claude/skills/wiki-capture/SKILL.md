---
name: wiki-capture
description: Use when capturing source files or URLs into raw/captures before an ingest, especially for .md, .txt, .docx, .pdf, .pptx, .xlsx, images, or URL material.
---

# Wiki Capture

Capture preserves source evidence and creates an ingest prompt. It does not replace the later LLM-owned wiki compilation step.

## Steps

1. Prefer `cwiki capture . <file-or-url> --title "<title>"`.
2. For `.txt` and `.md`, capture reads UTF-8 text directly.
3. For `.docx`, use `wiki-parse-docx`.
4. For `.pdf`, use `wiki-parse-pdf`; scanned PDFs should go through OCR before capture.
5. For images or embedded screenshots, use `wiki-parse-image`.
6. For `.pptx`, use `wiki-parse-pptx`.
7. For `.xlsx`, use `wiki-parse-xlsx`.
8. Confirm the generated raw record under `raw/captures/`.
9. Process the generated `.cwiki/prompts/ingest-*.md` with `wiki-ingest`.

## Rules

- Preserve the source language. Do not translate during capture or ingest unless the user explicitly asks.
- Never edit captured raw records unless the user explicitly asks.
- Keep private or copyrighted raw material out of git.
- If extraction is lossy or partial, say so before ingesting.
