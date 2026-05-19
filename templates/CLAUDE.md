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
- an overview map
- a synthesis thesis

The LLM creates pages, updates them when new sources arrive, maintains cross-references, and keeps the wiki consistent. The user reads it; the LLM writes it.

## Required Reading

Before any wiki operation, read:

1. `WIKI_SCHEMA.md`
2. `wiki/index.md`
3. The relevant pages under `wiki/`

Canonical skills live under `.claude/skills/`. Use them when a workflow matches.

## Execution Model

- The CLI is the scaffold and local utility layer: initialize, capture, index, lint, search, and generate prompts or briefs.
- `link-graph` and `link-graph-report` create a deterministic link graph from compiled wiki pages and `[[wikilinks]]`; `graph` and `graph-report` are compatibility aliases.
- Agent intelligence runs in the current agent platform. Use the current agent model for reasoning and final prose unless the user explicitly asks you to run a CLI command.
- Local skills are instructions for agents, not executable CLI plugins.
- `ask` and `web-ask` prepare evidence and prompts; they do not call an LLM.
- `answer` calls the `.env` configured provider/model against local wiki retrieval, but it does not perform live web search.
- Live web research requires a browser-capable agent following `wiki-agent-browser`.

## Hybrid Agent Query Workflow

Use this when answering inside an agent platform such as Codex, Trae, Claude Code, Cursor, or OpenCode.

1. Prefer the standard path first: run `cwiki ask . "<question>" --retrieval auto` when no suitable query prompt exists.
2. Read the generated `.cwiki/prompts/query-*.md` and `.cwiki/briefs/brief-*.md`; treat the prompt as the reproducible evidence boundary.
3. Read every relevant page listed in the prompt from disk, plus `wiki/index.md`.
4. If the prompt context is incomplete, search or inspect additional high-signal wiki pages and follow one level of useful `[[wikilinks]]`.
5. If the question needs current web evidence, use `cwiki web-ask . "<question>"` and `wiki-agent-browser`; do not invent current facts from memory.
6. Final prose comes from the current agent model, not `.env`, unless the user explicitly asks for `cwiki answer`.
7. Answer with `## Evidence Used`, `## Answer`, and `## Gaps`; cite `[[slug]]` pages and source paths or URLs near factual claims.
8. In `## Evidence Used`, mark prompt-listed pages as `used` or `not used - reason`, and list any extra pages or web sources discovered during hybrid exploration.

## Layered Retrieval Strategy

- `direct`: direct keyword/vector hits only; use for narrow fact lookup.
- `graph`: direct hits plus inbound/outbound wikilink neighbors from `.cwiki/graph/graph.json`; use when nearby concepts, roles, modules, or entities may matter. This is link navigation, not a typed entity-relation graph.
- `path`: direct hits plus graph neighbors plus shortest-path evidence between top hits; use for workflows, mechanisms, dependencies, relationships, and how/why questions.
- `synthesis`: direct hits plus graph context, path evidence, and global overview/synthesis/central pages; use for broad summaries, comparisons, tradeoffs, strategy, or evaluation.
- `auto`: CLI-selected layer. If `auto` selects `path` but finds no path evidence, it falls back to `graph` and records the fallback in Retrieval Trace.

For graph retrieval, refresh `cwiki link-graph-report .` after link or page changes. Read Retrieval Trace as the contract: direct hits are primary evidence, graph-expanded pages are nearby context, path evidence explains relationships, and final context pages are the reproducible evidence pack.

Use `cwiki ask . "<question>" --graph-rerank` or `cwiki answer . "<question>" --graph-rerank` when semantic reranking is worth an extra model call. Inspect the `LLM Graph Rerank` section before answering, but keep source-backed page evidence above rerank reasons.

## Local Configuration

- `.env.example` is the template for local model and web-search defaults.
- Copy `.env.example` to `.env` before running `cwiki answer` with provider API keys.
- `.env` is ignored by git and should not be committed.
- `.env` model settings affect terminal/CLI workflows such as `cwiki answer`; they do not change this agent platform's active chat model.
- `cwiki answer` uses the configured provider/model and local wiki retrieval, but it does not perform live web search.
- `web-ask` reads `.env` defaults such as `CWIKI_WEB_WIKI_WEIGHT`, `CWIKI_WEB_WEIGHT`, `CWIKI_WEB_MAX_SOURCES`, and `CWIKI_WEB_ENABLED`; command-line flags override them.
- `web-ask` creates browser research and fusion prompts; it does not execute browser research by itself.
- `answer --web-on-gaps` and `eval-answer --web-on-gaps` detect gaps that need external evidence, then create `.cwiki/web-gaps/`, `web-query-*`, `web-research-*`, `web-captures-*`, and `fusion-*` artifacts. They use the same `CWIKI_WEB_*` defaults unless `--web-gap-*` flags override them.
- The skill files in `.claude/skills/` and `.agents/skills/` are agent instructions, not executable CLI plugins.
- When working as an agent inside this wiki, use the current agent model for reasoning and final prose unless the user explicitly asks you to run a CLI command.
- The CLI automatically records model usage for `answer`, graph rerank, and `--llm` evaluation under `.cwiki/usage/llm-usage.jsonl`.
- If this agent platform exposes token or cost numbers for ingest, update, browser research, final answer, or other platform-model work, record them with `cwiki usage-log . --operation <step> --provider agent-platform --model <visible-model-name> ...`.
- Use `cwiki usage-report .` for a full cost report, or filter with `--operation`, `--artifact`, `--question`, `--provider`, `--model`, `--since`, and `--until`.
- For LLM-assisted evaluation inside an agent platform, use the current agent model rather than the `.env` model. Write the assisted assessment to `.cwiki/eval/agent-assisted-*.md`, then attach it with `--agent-eval-file <file> --agent-model <visible-model-name>` so the official report records `provider: agent-platform`.
- Prefer this folder's local instructions and skills before platform-specific skills: read `CLAUDE.md`, `AGENTS.md`, and `WIKI_SCHEMA.md`, then use `.claude/skills/` or `.agents/skills/` for capture, ingest, query, update, lint, and browser research.
- For wiki questions in an agent platform, prefer the hybrid query workflow: use `cwiki ask` for a stable prompt and evidence brief, then let the agent inspect additional wiki pages only when the prompt is incomplete.
- If the local skills do not cover the task, use your platform's own tools or an exploratory implementation, while preserving the wiki schema, source-citation rules, and operation log.
- If the user asks for web evidence, run `cwiki web-ask . "<question>"` when useful, read the generated prompts, perform browser research when enabled, and follow the configured weights during synthesis.
- If the user asks about relationships, impact, paths, central concepts, or graph structure, run `cwiki link-graph-report .`, `cwiki path . <a> <b>`, or `cwiki explain . <slug>` when useful.

## Directory Contract

```text
raw/              Human-owned immutable source material
wiki/             LLM-owned compiled knowledge layer
  overview.md     Durable map and early-stage entry point
  synthesis.md    Source-backed cross-page thesis for mature knowledge
  summaries/      Source and topic summaries
  entities/       People, organizations, places, products, projects
  concepts/       Ideas, theories, methods, terms
  comparisons/    Compare/contrast pages and decision matrices
  index.md        Content catalog
  log.md          Append-only operation log
.cwiki/prompts/   Generated working prompts, not knowledge
.cwiki/graph/     Generated link graph artifacts, not canonical knowledge
.cwiki/web-captures/ Web source capture checklists
.cwiki/ingest-runs/ Recoverable ingest workflow state
```

## Non-Negotiable Rules

- Never edit `raw/` unless the user explicitly asks.
- Do not put generated knowledge outside `wiki/`.
- Do not treat `.cwiki/prompts/` as knowledge.
- Do not treat `.cwiki/graph/` as canonical knowledge or a typed knowledge graph; regenerate it from `wiki/` when stale.
- Every factual claim needs a source path or URL.
- Preserve source language. Chinese sources should produce Chinese wiki pages; English sources should produce English wiki pages. Do not translate by default unless the user explicitly asks.
- Prefer updating existing wiki pages over creating isolated pages.
- Use Obsidian wikilinks like `[[retrieval-augmented-generation]]`.
- Keep contradictions visible until resolved.
- Update `wiki/index.md` after every ingest or saved analysis.
- Append to `wiki/log.md`; never rewrite historical log entries.
- Treat `wiki/overview.md` and `wiki/synthesis.md` as two alternative first reading surfaces, not placeholders. Use `overview.md` when the wiki needs orientation and navigation; use `synthesis.md` when the wiki has enough source-backed evidence for an integrated thesis.
- Refresh both `wiki/overview.md` and `wiki/synthesis.md` after every ingest or update. Do not leave generic seed prose once the wiki contains real ingested knowledge.

## Auto-Trigger Workflows

### Ingest

Trigger when the user says: ingest, process, add to wiki, summarize this source, read this URL/file, or points to a raw source.

If the source has not been captured yet, use `wiki-capture` first. For complex formats, route through the built-in parser skills before ingest: `wiki-parse-docx`, `wiki-parse-pdf`, `wiki-parse-image`, `wiki-parse-pptx`, or `wiki-parse-xlsx`.

Action:

1. Read the source in full.
2. Read `wiki/index.md` and relevant existing wiki pages.
3. Preserve the source language for generated wiki content unless the user explicitly asks for translation.
4. Identify affected summaries, entities, concepts, comparisons, overview, and synthesis.
5. Create or update pages under the correct `wiki/` section.
6. Refresh `wiki/overview.md` with the current map, entry links, and open navigation questions.
7. Refresh `wiki/synthesis.md` with stable claims, contradictions, evidence inventory, or why no thesis is promoted yet.
8. Add source-backed claim ledger rows.
9. Add bidirectional wikilinks where useful.
10. Run `cwiki index .`.
11. Run `cwiki link-graph-report .` after link changes.
12. Append to `wiki/log.md`.

### Query

Trigger when the user asks a question about wiki knowledge.

Action:

1. Prefer `wiki-query`: run `cwiki ask . "<question>" --retrieval auto` if no suitable query prompt already exists. Use `--retrieval graph` to inspect nearby concepts, `--retrieval path` for relationship/mechanism/workflow questions, and `--retrieval synthesis` for synthesis-heavy questions.
2. Read the generated query prompt and evidence brief.
3. Read the prompt's Retrieval Trace to understand direct hits, graph-expanded pages, and path evidence.
4. Read `wiki/index.md` and the relevant wiki pages in full.
5. Follow one level of relevant wikilinks when the prompt context is incomplete.
6. Answer with local citations like `[[topic]]` and source paths or URLs.
7. State gaps explicitly, including any extra pages inspected or prompt-listed pages that were not useful.
8. Offer to save substantial synthesis into `wiki/synthesis.md`, `wiki/comparisons/`, or another fitting wiki page.

### Graph

Trigger when the user asks about relationships, paths, impact analysis, central concepts, isolated pages, or graph structure.

Action:

1. Run `cwiki link-graph-report .`.
2. Read `.cwiki/graph/graph.md`.
3. Use `cwiki path . <from> <to>` for explicit relationship paths.
4. Use `cwiki explain . <slug>` for a node-level view.
5. Cite local pages as `[[slug]]` and mention when the graph only reflects existing wikilinks.

### Agent Browser

Trigger when the user asks for current, recent, latest, market, policy, pricing, benchmark, release, news, or any answer that needs live web evidence.

Action:

1. Use `wiki-agent-browser`.
2. Run `cwiki web-ask . "<question>"` if no web query prompt exists. Use `--web-weight 0` or `--no-web` when the user wants web search disabled.
3. Read local wiki context first.
4. Search and open web sources when web mode is enabled; never cite search result snippets.
5. Write web findings into `.cwiki/web-research/*.md`.
6. Update `.cwiki/web-captures/*.md` with durable-source decisions.
7. Read the generated `.cwiki/prompts/fusion-*.md` to produce the final answer.
8. Respect evidence weights from the prompt when reconciling local wiki and web evidence.
9. Answer with separate local wiki evidence, web evidence, synthesis, gaps, and sources.
10. Cite local pages as `[[slug]]`; cite external facts with exact URLs and access dates.
11. If the web source should become durable knowledge, run `cwiki capture . <url> --title "<title>"`, process the ingest prompt, update `wiki/index.md`, and append to `wiki/log.md`.

If a prior answer or evaluation already exists and its gaps say that case studies, metrics, current facts, or migration guidance are missing, run `cwiki eval-answer . <answer-file> --web-on-gaps` first. Use the generated web gap report and fusion prompt as the handoff for browser research.

### Update

Trigger when the user asks to revise, correct, merge, or reconcile wiki content.

Action:

1. Read affected pages.
2. Find inbound links to affected pages.
3. Apply source-cited edits.
4. Update `updated` frontmatter.
5. Refresh `wiki/overview.md` with the current page map, entry links, scope, and open navigation questions.
6. Refresh `wiki/synthesis.md` with the current thesis state, stable claims, contradictions, evidence inventory, or why no thesis is promoted yet.
7. Run `cwiki index .`.
8. Append to `wiki/log.md`.

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
cwiki link-graph-report .
cwiki web-ask . "<question>"
```

If `cwiki` is not installed globally, use the relative path to this project's `bin/cwiki.mjs`.
