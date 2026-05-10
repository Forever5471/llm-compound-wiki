---
name: wiki-capture
description: Use when capturing source files or URLs into raw/captures before an ingest, especially for .md, .txt, .docx, .pdf, or URL material.
---

# Wiki Capture

Capture preserves source evidence and creates an ingest prompt. It does not replace the later LLM-owned wiki compilation step.

## Steps

1. Prefer `cwiki capture . <file-or-url> --title "<title>"`.
2. For `.txt` and `.md`, capture reads UTF-8 text directly.
3. For `.docx`, capture extracts text from the Word document body using the built-in document parser.
4. For `.pdf`, capture requires a text extraction tool. If the CLI reports that PDF text extraction is unavailable, convert the PDF to text first, then run `cwiki capture` on the extracted `.txt`.
5. Confirm the generated raw record under `raw/captures/`.
6. Process the generated `.cwiki/prompts/ingest-*.md` with `wiki-ingest`.

## Rules

- Preserve the source language. Do not translate during capture or ingest unless the user explicitly asks.
- Never edit captured raw records unless the user explicitly asks.
- Keep private or copyrighted raw material out of git.
- If extraction is lossy or partial, say so before ingesting.

