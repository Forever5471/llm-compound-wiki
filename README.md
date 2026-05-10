# LLM Compound Wiki

[中文说明](README.zh-CN.md)

LLM Compound Wiki is an open-source scaffold for building a personal or team wiki that an AI agent continuously maintains.

It is inspired by Andrej Karpathy's `llm-wiki` prototype and existing community experiments, but this project takes a slightly different shape:

- agent-agnostic first: Codex, Claude Code, OpenCode, Cursor, or any filesystem-capable agent can use it
- Obsidian-friendly markdown by default
- zero-dependency Python CLI for repeatable initialization, indexing, search, and health checks
- explicit distinction between raw evidence and the LLM-owned compiled wiki layer

## Core Idea

Most RAG systems rediscover your source material on every query. A compound wiki does more of the work once.

When you add a source, the agent reads it, extracts durable claims, updates related pages, adds backlinks, flags contradictions, updates the index, and appends to a log. The wiki becomes a persistent compiled artifact, not a transient chat answer.

```text
raw/ source material
        |
        v
LLM agent reads, reconciles, links, cites
        |
        v
wiki/ summaries, entities, concepts, comparisons, overview, synthesis
```

## Repository Layout

```text
.
├── AGENTS.md                 Agent rules for this project
├── bin/cwiki.mjs             Zero-dependency CLI
├── templates/                Files copied into a new wiki
│   ├── AGENTS.md
│   ├── CLAUDE.md
│   ├── WIKI_SCHEMA.md
│   ├── .claude/skills/       Canonical skill definitions
│   └── .agents/skills/       Compatibility skill entrypoints
├── raw/                      Private immutable sources, ignored by git
├── .cwiki/prompts/           Generated ingest prompts, ignored by git
├── wiki/
│   ├── overview.md           Durable map of the knowledge base
│   ├── synthesis.md          Current integrated thesis
│   ├── summaries/            Source and topic summaries
│   ├── entities/             People, organizations, products, projects
│   ├── concepts/             Ideas, theories, methods, terms
│   ├── comparisons/          Compare/contrast and decision pages
│   ├── index.md              Content catalog
│   └── log.md                Append-only operation log
```

## Quick Start

Use directly from this checkout:

```bash
python3 ./bin/cwiki.py init ./my-wiki --domain "AI research notes"
cd my-wiki
python3 ../bin/cwiki.py lint .
```

If you still want an npm-style command, install from this checkout; the npm entrypoint simply delegates to Python:

```bash
npm install -g .
cwiki init ./my-wiki --domain "Market research"
cwiki search ./my-wiki "pricing"
cwiki lint ./my-wiki
```

The repository keeps a small `bin/cwiki.mjs` Node wrapper for npm compatibility. The actual implementation lives in `bin/cwiki.py`.

## CLI Commands

```bash
cwiki init <dir> [--domain "..."]
cwiki index <dir>
cwiki lint <dir>
cwiki search <dir> <query>
cwiki capture <dir> <file-or-url> [--title "..."]
```

`capture` does not summarize by itself. It creates a raw-source record and an ingest prompt for your agent. The agent then follows `WIKI_SCHEMA.md` and the skill files to compile the source into the right `wiki/` sections.

## Page Format

```markdown
---
title: Topic Name
kind: concept
tags: [tag-a, tag-b]
sources: 2
updated: 2026-05-08
status: active
---

# Topic Name

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| ... | raw/example.md | medium | 2026-05-08 |

## Synthesis

## Related

- [[another-topic]] - why it matters

## Open Questions
```

The claim ledger is the main difference from lighter templates. It makes the wiki auditable and helps later agents update specific claims instead of rewriting whole pages.

## Agent Workflow

1. Read `WIKI_SCHEMA.md` before changing wiki content.
2. Treat `raw/` as read-only evidence.
3. Put generated knowledge in the right wiki section: summaries, entities, concepts, comparisons, overview, or synthesis.
4. Every factual claim needs a source path or URL.
5. After ingesting or saving an analysis, run `cwiki index .`.
6. After several ingests, run `cwiki lint .` and fix broken links, stale claims, and orphan pages.

`CLAUDE.md` is generated for Claude Code and other agents that look for a root instruction file. `AGENTS.md` is the tool-agnostic entrypoint, and `WIKI_SCHEMA.md` is the detailed wiki contract.

The generated wiki also includes `wiki-init`, `wiki-ingest`, `wiki-query`, `wiki-update`, and `wiki-lint` skills under `.claude/skills/`, plus compatibility entrypoints under `.agents/skills/`.

## Design Principles

- Compiled knowledge beats repeated retrieval.
- Links are part of the knowledge, not decoration.
- The log is append-only, because the wiki's history is also evidence.
- Human judgment directs source selection and emphasis.
- The agent handles bookkeeping, cross-references, and consistency.

## License

MIT
