# AGENTS.md

This repository builds and ships the LLM Compound Wiki scaffold.

## Purpose

The project contains:

- a zero-dependency CLI in `bin/cwiki.mjs`
- reusable wiki templates in `templates/`
- tests in `test/`
- optional sample wiki folders created by `cwiki init`

## Engineering Rules

- Keep the CLI dependency-free unless there is a strong reason to add a package.
- Do not modify user source material under any `raw/` directory.
- Template files should be agent-agnostic and work for Codex, Claude Code, OpenCode, Cursor, and similar agents.
- Use plain Markdown and Obsidian wikilinks (`[[slug]]`) for interoperability.
- Update tests when CLI behavior changes.

## Wiki Philosophy

The wiki has three layers:

- `raw/`: immutable source evidence owned by the human
- `wiki/`: AI-maintained compiled knowledge, including summaries, entities, concepts, comparisons, overview, and synthesis

The agent's job is not merely to retrieve. It should integrate, cite, cross-link, and maintain the compiled layer over time.
