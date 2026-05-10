---
name: wiki-update
description: Use when revising existing wiki pages based on new evidence, user correction, or a lint finding.
---

# Wiki Update

Updates must be traceable.

## Steps

1. Read `WIKI_SCHEMA.md`.
2. Read the target page in full.
3. Search for pages that link to it.
4. Propose the change with source evidence.
5. Apply the smallest edit that resolves the issue.
6. Update frontmatter `updated`.
7. If the update changes the global picture, update `wiki/overview.md` or `wiki/synthesis.md`.
8. Run `cwiki index .`.
9. Append to `wiki/log.md`.

If new evidence contradicts old content, preserve the contradiction explicitly until the user or sources resolve it.
