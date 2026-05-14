# Answering Workflow

This document describes the recommended question-answering paths for an initialized LLM Compound Wiki.

## Modes

### CLI prompt preparation

`cwiki ask <dir> "<question>"` does not call a model. It retrieves local wiki context and writes:

- `.cwiki/prompts/query-*.md` for an answering agent or LLM.
- `.cwiki/briefs/brief-*.md` for quick human inspection.

Use this when you want a reproducible evidence boundary before an agent writes final prose.

### CLI model answering

`cwiki answer <dir> "<question>"` calls the `.env` configured provider/model and writes a draft under `.cwiki/answers/`.

This path is terminal-oriented. It uses local wiki retrieval and the configured model, but it does not perform live web search.

### Agent-platform hybrid answering

Use this path inside Codex, Trae, Claude Code, Cursor, OpenCode, or another filesystem-capable agent.

1. Run `cwiki ask . "<question>"` when no suitable query prompt exists.
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
