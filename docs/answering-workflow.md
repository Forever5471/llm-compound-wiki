# Answering Workflow

This document describes the recommended question-answering paths for an initialized LLM Compound Wiki.

## Modes

### CLI prompt preparation

`cwiki ask <dir> "<question>"` does not call a model. It retrieves local wiki context and writes:

- `.cwiki/prompts/query-*.md` for an answering agent or LLM.
- `.cwiki/briefs/brief-*.md` for quick human inspection.

Use this when you want a reproducible evidence boundary before an agent writes final prose.

Use `--retrieval auto|direct|graph|path|synthesis` to control how much graph-aware context is added. `auto` classifies question complexity and records the chosen strategy in the prompt's Retrieval Trace.

### Layered retrieval strategy

- `direct`: direct keyword/vector hits only. Use for narrow fact lookup.
- `graph`: direct hits plus inbound/outbound wikilink neighbors from the generated graph. Use when nearby concepts, roles, modules, or related entities may matter.
- `path`: graph context plus shortest-path evidence between top hits. Use for workflows, mechanisms, dependencies, relationships, and how/why questions.
- `synthesis`: direct, graph, path, overview/synthesis, and central-node context. Use for broad summaries, comparisons, tradeoffs, strategy, and evaluation.
- `auto`: CLI-selected layer. If `auto` selects `path` but finds no path evidence, it falls back to `graph` and records the fallback in Retrieval Trace.

Graph retrieval does not treat the graph as a fact source. `.cwiki/graph/graph.json` is a navigation layer: Direct Hits are primary evidence, Graph-Expanded Pages are nearby context, Path Evidence explains relationships, and Final Context Pages define the reproducible evidence pack.

### CLI model answering

`cwiki answer <dir> "<question>"` calls the `.env` configured provider/model and writes a draft under `.cwiki/answers/`.

This path is terminal-oriented. It uses local wiki retrieval and the configured model, but it does not perform live web search.

It uses the same retrieval strategy options as `ask`, so answer evaluation can later inspect the linked query prompt and score retrieval quality.

### Agent-platform hybrid answering

Use this path inside Codex, Trae, Claude Code, Cursor, OpenCode, or another filesystem-capable agent.

1. Run `cwiki ask . "<question>" --retrieval auto` when no suitable query prompt exists.
2. Read the generated query prompt and evidence brief.
3. Read every prompt-listed wiki page from disk, plus `wiki/index.md`.
4. Treat the prompt as the reproducible evidence boundary.
5. If the context pack is incomplete, inspect additional high-signal wiki pages and follow one level of useful `[[wikilinks]]`.
6. If the question needs current web evidence, run `cwiki web-ask . "<question>"` and follow `wiki-agent-browser`.
7. Generate final prose with the current agent-platform model, not the project's `.env` model, unless the user explicitly asks for `cwiki answer`.

## Answer Shape

Hybrid answers should use:

```markdown
## Evidence Used

- [[page-a]] - used - source: raw/example.md
- [[page-b]] - not used - reason: adjacent but not needed for this question
- [[extra-page]] - used - source: raw/other.md

## Answer

Direct answer with `[[page-a]]` citations and source paths or URLs near factual claims.

## Gaps

Known missing evidence, weak coverage, limitations, unused relevant pages, or "No known gaps from the inspected wiki context."
```

## Why Hybrid

The generated prompt keeps answers auditable and repeatable. The agent's extra inspection prevents a single under-retrieved context pack from becoming an artificial limit. The final answer must still remain grounded in wiki pages, source paths, URLs, and explicit gaps.
