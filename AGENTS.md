# AGENTS.md

This repository builds and ships the LLM Compound Wiki scaffold.

## Purpose

The project contains:

- a zero-dependency Python CLI in `bin/cwiki.py`
- an npm/Node compatibility wrapper in `bin/cwiki.mjs`
- reusable wiki templates in `templates/`
- tests in `test/`
- optional sample wiki folders created by `cwiki init`

## Engineering Rules

- Keep the CLI dependency-free unless there is a strong reason to add a package.
- Do not modify user source material under any `raw/` directory.
- Template files should be agent-agnostic and work for Codex, Claude Code, OpenCode, Cursor, and similar agents.
- Use plain Markdown and Obsidian wikilinks (`[[slug]]`) for interoperability.
- Update tests when CLI behavior changes.
- When adding or changing agent-facing behavior, update both the root project docs and the generated wiki templates under `templates/`.

## Wiki Philosophy

The wiki has three layers:

- `raw/`: immutable source evidence owned by the human
- `wiki/`: AI-maintained compiled knowledge, including summaries, entities, concepts, comparisons, overview, and synthesis
- `.cwiki/`: generated working artifacts such as ingest prompts, query prompts, briefs, web research notes, and draft answers

The agent's job is not merely to retrieve. It should integrate, cite, cross-link, and maintain the compiled layer over time.

## Current Capabilities

The CLI supports:

- `init`: scaffold a new wiki with schema, agent instructions, and skills
- `capture`: record URLs and source files under `raw/captures/`
- `index` and `lint`: maintain wiki consistency
- `search` and `ask`: retrieve from the compiled local wiki
- `answer`: call a configured model against local wiki context
- `web-ask`: create a browser research workflow that combines local wiki evidence with current web evidence

`web-ask` generates:

- `.cwiki/prompts/web-query-*.md` for browser research
- `.cwiki/web-research/web-research-*.md` for auditable web findings
- `.cwiki/prompts/fusion-*.md` for final synthesis across local and web evidence
- `.cwiki/briefs/web-brief-*.md` for human-readable task summaries

Evidence fusion supports default weights from `.env`:

```bash
CWIKI_WEB_WIKI_WEIGHT=0.6
CWIKI_WEB_WEIGHT=0.4
CWIKI_WEB_MAX_SOURCES=6
CWIKI_WEB_ENABLED=true
```

Command-line flags take precedence. Use `--web-weight 0` or `--no-web` to disable browsing and produce a local-wiki-only fusion prompt.
