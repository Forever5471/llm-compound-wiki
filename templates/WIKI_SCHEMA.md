# LLM Compound Wiki Schema

Domain: {{domain}}

Created: {{date}}

## What This Is

This wiki is a persistent compiled knowledge base maintained by an AI agent.

The human curates sources and sets direction. The agent reads sources, extracts claims, updates wiki pages, creates links, tracks contradictions, updates the index, and appends to the log.

## Directory Structure

```text
raw/              Immutable source material
wiki/
  overview.md     High-level map of the whole wiki
  synthesis.md    Current cross-source synthesis
  summaries/      Source and topic summaries
  entities/       People, organizations, places, products, projects
  concepts/       Ideas, theories, methods, terms
  comparisons/    Compare/contrast pages and decision matrices
  index.md        Content catalog
  log.md          Append-only operation log
.cwiki/prompts/   Generated ingest prompts and local working notes
```

## Page Rules

- All LLM-generated knowledge pages live under `wiki/`.
- Preserve source language during ingest. Chinese sources should be compiled into Chinese wiki pages; English sources into English wiki pages. Do not translate by default unless the user explicitly asks.
- Pick the most specific wiki section:
  - `wiki/summaries/<slug>.md` for source summaries and compact topic summaries
  - `wiki/entities/<slug>.md` for people, organizations, places, products, projects
  - `wiki/concepts/<slug>.md` for ideas, theories, methods, terms
  - `wiki/comparisons/<slug>.md` for compare/contrast pages
  - `wiki/overview.md` for the durable map of the knowledge base
  - `wiki/synthesis.md` for the current integrated thesis across sources
- Filenames are lowercase slugs: `retrieval-augmented-generation.md`.
- Use Obsidian wikilinks: `[[retrieval-augmented-generation]]`.
- Every generated wiki page must include YAML frontmatter:

```yaml
---
title: Topic Name
kind: concept
tags: [tag-a, tag-b]
sources: 1
updated: YYYY-MM-DD
status: active
---
```

## Topic Page Template

```markdown
---
title: Topic Name
kind: concept
tags: [tag-a]
sources: 1
updated: YYYY-MM-DD
status: active
---

# Topic Name

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| A concise factual claim. | raw/source.md | medium | YYYY-MM-DD |

## Synthesis

What the wiki currently believes, in prose.

## Related

- [[related-topic]] - relationship

## Contradictions

- None known.

## Open Questions

- What should be investigated next?
```

## Ingest Workflow

1. Read the source in full. For long documents, process section by section.
2. Read `wiki/index.md` and any relevant existing pages.
3. Tell the user the likely pages and claims that will be added or updated.
4. Preserve the source language in generated wiki content unless the user explicitly asks for translation.
5. Write or update the right wiki pages:
   - `wiki/summaries/` for the source summary
   - `wiki/entities/` for durable entity pages
   - `wiki/concepts/` for reusable concepts
   - `wiki/comparisons/` when the source changes a comparison
   - `wiki/overview.md` and `wiki/synthesis.md` when the global map or thesis changes
6. Add source-backed rows to the claim ledger.
7. Add links from new pages to existing pages and from existing pages back to new pages where appropriate.
8. Run `cwiki index .`.
9. Append to `wiki/log.md`.

## Query Workflow

1. Read `wiki/index.md` first.
2. Read relevant wiki pages in full across `summaries/`, `entities/`, `concepts/`, `comparisons/`, `overview.md`, and `synthesis.md`.
3. Follow one level of relevant `[[wikilinks]]`.
4. Answer using local page citations like `[[topic]]` and source paths or URLs.
5. State gaps explicitly.
6. Offer to save substantial answers into the appropriate wiki section, commonly `wiki/comparisons/` or by updating `wiki/synthesis.md`.

## Lint Workflow

Run `cwiki lint .` and inspect:

- broken wikilinks
- missing frontmatter fields
- orphan pages
- pages with stale wording such as "latest", "current", or "recent"
- concepts referenced often but lacking dedicated pages

Fixes should be small, source-cited, and logged.

## Log Format

Append entries to `wiki/log.md`:

```markdown
## [YYYY-MM-DD] operation | title
- Pages: [[page-a]], [[page-b]]
- Sources: raw/example.md
- Summary: What changed and why.
```
