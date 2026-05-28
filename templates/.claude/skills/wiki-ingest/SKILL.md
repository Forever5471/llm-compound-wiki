---
name: wiki-ingest
description: Use when adding a source file, URL, transcript, paper, note, or pasted text to the wiki.
---

# Wiki Ingest

Ingest turns raw evidence into compiled wiki pages.

## Steps

1. Read `WIKI_SCHEMA.md`.
2. Read the source in full. If it is a URL capture, fetch the URL and cite it.
3. Read `wiki/index.md`.
4. Read all existing pages that seem related.
5. Briefly tell the user what pages and claims you plan to add or update.
6. Preserve the source language. Chinese sources produce Chinese wiki pages; English sources produce English wiki pages. Do not translate by default unless the user asks.
7. Create or update generated wiki pages:
   - `wiki/summaries/` for source or topic summaries
   - `wiki/entities/` for people, organizations, projects, products, places
   - `wiki/concepts/` for ideas, theories, methods, terms
   - `wiki/comparisons/` for compare/contrast pages
8. Mandatory global pages refresh:
   - Open both `wiki/overview.md` and `wiki/synthesis.md` on every ingest.
   - Update `overview.md` every time with the current map: scope, important page clusters, new or changed entry links, and open navigation questions.
   - Update `synthesis.md` every time with the current integrated thesis state: promoted stable claims, contradictions, evidence inventory, or a clear note that no thesis is promoted yet and why.
   - If either page still has `status: seed`, replace seed guidance with real wiki-specific content. Do not leave generic placeholder prose after the first real ingest.
   - Preserve source language for these pages where practical; if the wiki is mixed-language, prefer the dominant wiki language and keep titles/links exact.
9. Put factual claims in the page's claim ledger with a source path or URL.
10. Add `[[wikilinks]]` in both directions when pages clearly relate.
11. Run `cwiki ingest-finalize . --source-id <source_id>` after canonical page edits are complete.
12. Review `wiki/indexes/link-suggestions.md` for missed cross-links.
13. Run `cwiki backlinks check .`; use `cwiki backlinks apply .` only after reviewing managed backlink changes.
14. If the agent platform shows token or cost numbers for this ingest, record them with `cwiki usage-log . --operation ingest --provider agent-platform --model <visible-model-name> ...`.

For recoverable runs, create or update `.cwiki/ingest-runs/` state with:

```bash
cwiki ingest-plan . --source <raw-file>
cwiki ingest-step . <run-id> apply --status completed --note "wiki pages updated"
cwiki ingest-step . <run-id> validate --status completed
```

## Required Output

Tell the user:

- source processed
- pages created
- pages updated
- what changed in `wiki/overview.md`
- what changed in `wiki/synthesis.md`
- important contradictions or uncertainty
- any follow-up sources worth adding
- whether platform-model usage was recorded or unavailable

Never modify files under `raw/`.
