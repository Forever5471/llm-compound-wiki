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
7. Mandatory global pages refresh:
   - Open both `wiki/overview.md` and `wiki/synthesis.md` on every update.
   - Update `overview.md` every time with any changed navigation, scope, entry links, page clusters, or open map questions.
   - Update `synthesis.md` every time with any changed integrated thesis, stable claims, contradictions, evidence inventory, or a clear note that the update did not promote a thesis and why.
   - If either page still has `status: seed`, replace seed guidance with real wiki-specific content once any real wiki page exists. Do not leave generic placeholder prose in a wiki that already contains ingested knowledge.
8. In your final note, explicitly summarize what changed in `wiki/overview.md` and `wiki/synthesis.md`.
9. Run `cwiki ingest-finalize .` to refresh index, graph, hot/stale, link suggestions, backlink indexes, log shards, and `.cwiki/manifest.json`.
10. Review `wiki/indexes/link-suggestions.md` and run `cwiki backlinks check .` when links changed.
11. If the agent platform shows token or cost numbers for this update, record them with `cwiki usage-log . --operation update --provider agent-platform --model <visible-model-name> ...`.

If new evidence contradicts old content, preserve the contradiction explicitly until the user or sources resolve it.
