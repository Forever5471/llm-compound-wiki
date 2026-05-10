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
6. Create or update generated wiki pages:
   - `wiki/summaries/` for source or topic summaries
   - `wiki/entities/` for people, organizations, projects, products, places
   - `wiki/concepts/` for ideas, theories, methods, terms
   - `wiki/comparisons/` for compare/contrast pages
   - `wiki/overview.md` and `wiki/synthesis.md` when the global map or thesis changes
7. Put factual claims in the page's claim ledger with a source path or URL.
8. Add `[[wikilinks]]` in both directions when pages clearly relate.
9. Run `cwiki index .`.
10. Append to `wiki/log.md`.

## Required Output

Tell the user:

- source processed
- pages created
- pages updated
- whether `overview.md` or `synthesis.md` changed
- important contradictions or uncertainty
- any follow-up sources worth adding

Never modify files under `raw/`.
