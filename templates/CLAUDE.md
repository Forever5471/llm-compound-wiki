# LLM Compound Wiki — Agent Instructions

Domain: {{domain}}

Today's date: {{date}}

> CRITICAL: This repository is an LLM-maintained wiki. The human owns `raw/`; the LLM owns `wiki/`.

## What This Is

This is a compounding wiki inspired by Karpathy's LLM Wiki pattern.

The wiki layer is a directory of LLM-generated markdown files:

- summaries
- entity pages
- concept pages
- comparisons
- an overview
- a synthesis

The LLM creates pages, updates them when new sources arrive, maintains cross-references, and keeps the wiki consistent. The user reads it; the LLM writes it.

## Required Reading

Before any wiki operation, read:

1. `WIKI_SCHEMA.md`
2. `wiki/index.md`
3. The relevant pages under `wiki/`

Canonical skills live under `.claude/skills/`. Use them when a workflow matches.

## Directory Contract

```text
raw/              Human-owned immutable source material
wiki/             LLM-owned compiled knowledge layer
  overview.md     Durable map of the whole wiki
  synthesis.md    Current integrated thesis across sources
  summaries/      Source and topic summaries
  entities/       People, organizations, places, products, projects
  concepts/       Ideas, theories, methods, terms
  comparisons/    Compare/contrast pages and decision matrices
  index.md        Content catalog
  log.md          Append-only operation log
.cwiki/prompts/   Generated working prompts, not knowledge
```

## Non-Negotiable Rules

- Never edit `raw/` unless the user explicitly asks.
- Do not put generated knowledge outside `wiki/`.
- Do not treat `.cwiki/prompts/` as knowledge.
- Every factual claim needs a source path or URL.
- Preserve source language. Chinese sources should produce Chinese wiki pages; English sources should produce English wiki pages. Do not translate by default unless the user explicitly asks.
- Prefer updating existing wiki pages over creating isolated pages.
- Use Obsidian wikilinks like `[[retrieval-augmented-generation]]`.
- Keep contradictions visible until resolved.
- Update `wiki/index.md` after every ingest or saved analysis.
- Append to `wiki/log.md`; never rewrite historical log entries.

## Auto-Trigger Workflows

### Ingest

Trigger when the user says: ingest, process, add to wiki, summarize this source, read this URL/file, or points to a raw source.

If the source has not been captured yet, use `wiki-capture` first. For complex formats, route through the dedicated parser skills before ingest: `wiki-parse-docx`, `wiki-parse-pdf`, `wiki-parse-image`, or `wiki-parse-pptx`.

Action:

1. Read the source in full.
2. Read `wiki/index.md` and relevant existing wiki pages.
3. Preserve the source language for generated wiki content unless the user explicitly asks for translation.
4. Identify affected summaries, entities, concepts, comparisons, overview, and synthesis.
5. Create or update pages under the correct `wiki/` section.
6. Add source-backed claim ledger rows.
7. Add bidirectional wikilinks where useful.
8. Run `cwiki index .`.
9. Append to `wiki/log.md`.

### Query

Trigger when the user asks a question about wiki knowledge.

Action:

1. Read `wiki/index.md` first.
2. Read relevant wiki pages in full.
3. Follow one level of relevant wikilinks.
4. Answer with local citations like `[[topic]]` and source paths or URLs.
5. State gaps explicitly.
6. Offer to save substantial synthesis into `wiki/synthesis.md`, `wiki/comparisons/`, or another fitting wiki page.

### Update

Trigger when the user asks to revise, correct, merge, or reconcile wiki content.

Action:

1. Read affected pages.
2. Find inbound links to affected pages.
3. Apply source-cited edits.
4. Update `updated` frontmatter.
5. Update `wiki/overview.md` or `wiki/synthesis.md` if the global picture changes.
6. Run `cwiki index .`.
7. Append to `wiki/log.md`.

### Lint

Trigger when the user asks for health check, lint, cleanup, consistency check, or after several ingests.

Action:

1. Run `cwiki lint .`.
2. Fix broken links, missing frontmatter, stale claims, misplaced pages, and orphan pages as appropriate.
3. Run `cwiki index .`.
4. Append to `wiki/log.md`.

## CLI

Use the local CLI when available:

```bash
cwiki index .
cwiki lint .
cwiki search . "<query>"
```

If `cwiki` is not installed globally, use the relative path to this project's `bin/cwiki.mjs`.
