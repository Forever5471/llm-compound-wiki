---
name: wiki-parse-image
description: Use when capturing or preparing images for wiki ingest, including screenshots, scanned pages, diagrams, charts, handwritten notes, and embedded document images.
---

# Wiki Parse Image

Goal: turn an image into auditable text, visual descriptions, and extraction notes for wiki ingest.

## Built-In Parser

Use built-in agent vision/OCR capability first when available in the current environment. Do not require cloning or calling external GitHub projects.

For `cwiki capture . <image-file>`, the CLI records an image raw reference and points the ingesting agent back to this skill. The skill is responsible for turning the image into auditable OCR text and visual notes before claims enter the wiki.

This project does not automatically search GitHub or integrate external OCR projects. If built-in image recognition is not good enough, tell the user to convert the image content to Markdown or UTF-8 text with a tool of their choice, then capture that converted file.

## Workflow

1. Identify image type: text scan, UI screenshot, chart, diagram, photo, or mixed.
2. Extract visible text using built-in OCR or vision.
3. Add a concise visual description for non-text meaning.
4. Capture the OCR/description as a text source with `cwiki capture`, or keep the image raw reference and include OCR/description in the ingest output.
5. During ingest, separate observed facts from interpretation.

## Quality Checks

- Include OCR confidence or uncertainty when available.
- Preserve original language.
- Flag tables, charts, and diagrams that require manual verification.
