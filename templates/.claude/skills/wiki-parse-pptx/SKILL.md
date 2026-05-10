---
name: wiki-parse-pptx
description: Use when capturing or preparing PowerPoint .pptx files for wiki ingest, including slide titles, speaker notes, diagrams, charts, and embedded images.
---

# Wiki Parse PPTX

Goal: convert a `.pptx` deck into slide-ordered Markdown or UTF-8 text for wiki ingest.

## Built-In Parser

Use the repository's built-in parser first:

```bash
cwiki capture . <file.pptx> --title "<title>"
```

The CLI reads the `.pptx` OOXML package directly, extracts slide text in slide order, and emits `Slide N` sections. It does not require external GitHub projects.

For image-heavy slides, screenshots, diagrams, charts, and SmartArt where meaning is not present as extractable text, route those visuals through `wiki-parse-image`.

## Workflow

1. Preserve slide order and slide numbers.
2. Extract slide title, bullets, and visible text.
3. Record omitted images/charts as extraction notes.
4. Capture the extracted Markdown/text with `cwiki capture`.
5. Process the generated ingest prompt with `wiki-ingest`.

## Quality Checks

- Check that slide order, titles, and section dividers survived.
- Flag charts and diagrams whose meaning is not recoverable from text alone.
- Preserve source language and do not translate unless requested.
