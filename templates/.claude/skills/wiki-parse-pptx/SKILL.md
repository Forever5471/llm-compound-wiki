---
name: wiki-parse-pptx
description: Use when capturing or preparing PowerPoint .pptx files for wiki ingest, including slide titles, speaker notes, diagrams, charts, and embedded images.
---

# Wiki Parse PPTX

Goal: convert a `.pptx` deck into slide-ordered Markdown or UTF-8 text for wiki ingest.

## Preferred Tool Order

1. Prefer structure-aware parsers such as Docling, MarkItDown, Unstructured, or MinerU when available.
2. If no parser is available, extract slide XML text and notes with a lightweight OOXML parser or export slides to text.
3. For image-heavy slides, route screenshots, diagrams, and charts through `wiki-parse-image`.

## Workflow

1. Preserve slide order and slide numbers.
2. Extract slide title, bullets, speaker notes, and visible text.
3. Record omitted images/charts as extraction notes.
4. Capture the extracted Markdown/text with `cwiki capture`.
5. Process the generated ingest prompt with `wiki-ingest`.

## Quality Checks

- Check that slide order, titles, and section dividers survived.
- Flag charts and diagrams whose meaning is not recoverable from text alone.
- Preserve source language and do not translate unless requested.

