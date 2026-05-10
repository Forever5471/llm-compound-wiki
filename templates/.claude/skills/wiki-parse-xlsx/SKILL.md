---
name: wiki-parse-xlsx
description: Use when capturing or preparing Excel .xlsx files for wiki ingest, including sheets, tables, metrics, formulas, and business data dictionaries.
---

# Wiki Parse XLSX

Goal: convert an `.xlsx` workbook into sheet-ordered Markdown or UTF-8 text for wiki ingest.

## Built-In Parser

Use the repository's built-in parser first:

```bash
cwiki capture . <file.xlsx> --title "<title>"
```

The CLI reads the `.xlsx` OOXML package directly, extracts shared strings and worksheet cell values, and emits `Sheet N` sections. It does not require external GitHub projects.

## Workflow

1. Preserve workbook and sheet order.
2. Extract visible cell values into row-oriented text.
3. Identify likely headers, metric names, dimensions, dates, and units.
4. Preserve source language; do not translate.
5. Capture the extracted text with `cwiki capture`.
6. Process the generated ingest prompt with `wiki-ingest`.

## Quality Checks

- Flag formulas, charts, pivot tables, hidden rows/sheets, merged-cell meaning, and formatting-only semantics as possible extraction gaps.
- For business metrics, preserve units, periods, and source sheet references.
- Do not infer unstated calculations unless the source file makes them explicit.

