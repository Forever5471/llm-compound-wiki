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
  overview.md     Durable map and early-stage entry point
  synthesis.md    Source-backed cross-page thesis for mature knowledge
  summaries/      Source and topic summaries
  entities/       People, organizations, places, products, projects
  concepts/       Ideas, theories, methods, terms
  comparisons/    Compare/contrast pages and decision matrices
  index.md        Content catalog
  log.md          Append-only operation log
.cwiki/prompts/   Generated ingest prompts and local working notes
.cwiki/graph/     Generated graph artifacts from compiled wiki links
```

## Page Rules

- All LLM-generated knowledge pages live under `wiki/`.
- Preserve source language during ingest. Chinese sources should be compiled into Chinese wiki pages; English sources into English wiki pages. Do not translate by default unless the user explicitly asks.
- Pick the most specific wiki section:
  - `wiki/summaries/<slug>.md` for source summaries and compact topic summaries
  - `wiki/entities/<slug>.md` for people, organizations, places, products, projects
  - `wiki/concepts/<slug>.md` for ideas, theories, methods, terms
  - `wiki/comparisons/<slug>.md` for compare/contrast pages
  - `wiki/overview.md` for the durable map of the knowledge base and the default entry point while evidence is still sparse
  - `wiki/synthesis.md` for the current integrated thesis across sources once there is enough source-backed material
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

## Overview And Synthesis

`overview.md` and `synthesis.md` are not placeholders. They are two alternative first reading surfaces:

- Use `overview.md` as the first screen when the wiki is still accumulating sources. It should orient a reader or agent: scope, important pages, navigation paths, and open map questions.
- Use `synthesis.md` as the first screen when the wiki has enough source-backed pages to support a durable integrated thesis. It should summarize what the wiki currently believes, what is stable, what is contested, and what evidence would change the conclusion.

Keep both pages lightweight and useful. Do not duplicate `wiki/index.md`; link to the most important pages with short reasons. Every ingest or update must refresh both files: `overview.md` should reflect the current map and entry links, while `synthesis.md` should reflect the current thesis state, contradictions, evidence inventory, or why no thesis has been promoted yet.

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
   - `wiki/overview.md` and `wiki/synthesis.md` on every ingest as the mandatory global pages refresh
6. Add source-backed rows to the claim ledger.
7. Add links from new pages to existing pages and from existing pages back to new pages where appropriate.
8. Before finishing, verify `wiki/overview.md` and `wiki/synthesis.md` no longer contain generic seed prose once real wiki knowledge exists.
9. Run `cwiki index .`.
10. Append to `wiki/log.md`.

## Query Workflow

For agent-platform use, query should be hybrid: the generated prompt provides a stable evidence boundary, and the agent may inspect more wiki pages only when that boundary is incomplete.

1. Run `cwiki ask . "<question>" --retrieval auto` when no suitable query prompt exists.
2. Read the generated `.cwiki/prompts/query-*.md` and `.cwiki/briefs/brief-*.md`.
3. Read the Retrieval Trace to see the chosen strategy, direct hits, graph-expanded pages, path evidence, and final context pages.
4. Read `wiki/index.md` first.
5. Read relevant wiki pages in full across `summaries/`, `entities/`, `concepts/`, `comparisons/`, `overview.md`, and `synthesis.md`.
6. Follow one level of relevant `[[wikilinks]]` when the prompt context is insufficient.
7. Answer using local page citations like `[[topic]]` and source paths or URLs.
8. Use the sections `## Evidence Used`, `## Answer`, and `## Gaps`.
9. In `## Evidence Used`, mark prompt-listed pages as used or not used, and list any extra pages discovered during hybrid exploration.
10. State gaps explicitly.
11. Offer to save substantial answers into the appropriate wiki section, commonly `wiki/comparisons/` or by updating `wiki/synthesis.md`.

### Retrieval Layers

- `direct`: direct keyword/vector hits only; use for narrow fact lookup.
- `graph`: direct hits plus inbound/outbound wikilink neighbors from the generated graph; use for nearby concepts, roles, modules, and related entities.
- `path`: direct hits plus graph neighbors plus shortest-path evidence between top hits; use for workflows, mechanisms, dependencies, relationships, and how/why questions.
- `synthesis`: direct hits plus graph context, path evidence, and overview/synthesis/central pages; use for broad summaries, comparisons, tradeoffs, strategy, and evaluation.
- `auto`: CLI-selected layer. If `auto` selects `path` but no path evidence exists, it falls back to `graph` and records the fallback in Retrieval Trace.

## Graph Workflow

Use this when a question is about relationships, paths, impact, central pages, or graph structure.

1. Run `cwiki graph-report .` to generate `.cwiki/graph/graph.json` and `.cwiki/graph/graph.md`.
2. Treat the graph as a derived navigation artifact. The canonical knowledge remains in `wiki/`.
3. Use `cwiki path . <from> <to>` for shortest wikilink paths.
4. Use `cwiki explain . <slug>` for inbound links, outbound links, and claim sources.
5. If the graph reveals missing links or broken links, update the relevant wiki pages with source-cited edits, then rerun `cwiki index .` and `cwiki graph-report .`.

## Agent Browser Workflow

Use this when a question needs current web evidence in addition to the compiled wiki.

1. Run `cwiki web-ask . "<question>"` to create a browser-agent prompt, web research workspace, and evidence fusion prompt.
2. Read the generated `.cwiki/prompts/web-query-*.md`.
3. Read local wiki context before browsing.
4. Respect evidence weights in the prompt. Use `--web-weight 0` or `--no-web` to disable browsing.
5. Search the web when enabled, open each cited source, and avoid citing search result snippets.
6. Prefer primary sources and durable references over summaries or scraped pages.
7. Write web findings into `.cwiki/web-research/*.md`.
8. Read `.cwiki/prompts/fusion-*.md` to produce the final answer.
9. Answer with separate local wiki evidence, web evidence, synthesis, gaps, and sources.
10. Cite local pages as `[[topic]]`; cite web facts with exact URLs and access dates.
11. If web evidence should become durable wiki knowledge, capture the URL with `cwiki capture`, then ingest it into `wiki/` with source-backed claim ledger rows.

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
