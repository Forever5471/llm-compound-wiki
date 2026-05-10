---
name: wiki-parse-image
description: Use when capturing or preparing images for wiki ingest, including screenshots, scanned pages, diagrams, charts, handwritten notes, and embedded document images.
---

# Wiki Parse Image

Goal: turn an image into auditable text, visual descriptions, and extraction notes for wiki ingest.

## Preferred Tool Order

1. For OCR text, use local OCR such as Tesseract/EasyOCR/PaddleOCR when available.
2. For charts, UI screenshots, diagrams, or dense visual context, use a vision-language model if allowed by the user.
3. For document images inside PDFs/DOCX/PPTX, extract the image reference and parse it separately rather than silently dropping it.

## Workflow

1. Identify image type: text scan, UI screenshot, chart, diagram, photo, or mixed.
2. Extract visible text with OCR.
3. Add a concise visual description for non-text meaning.
4. Capture the OCR/description as a text source with `cwiki capture`.
5. During ingest, separate observed facts from interpretation.

## Quality Checks

- Include OCR confidence or uncertainty when available.
- Preserve original language.
- Flag tables, charts, and diagrams that require manual verification.

