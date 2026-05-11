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
7. If the update changes the global picture, update `wiki/overview.md` when navigation, scope, or entry links change; update `wiki/synthesis.md` when the integrated thesis, stable claims, or contradictions change.
8. If `wiki/overview.md` or `wiki/synthesis.md` still has `status: seed`, replace seed guidance with real content once the update provides enough evidence. If not, leave it as seed and explain why.
9. Run `cwiki index .`.
10. Append to `wiki/log.md`.

If new evidence contradicts old content, preserve the contradiction explicitly until the user or sources resolve it.
