# AGENTS.md

This is an LLM Compound Wiki.

## Layer Rules

- `raw/` contains immutable source material. Never edit or delete raw files unless the user explicitly asks.
- `wiki/` contains the AI-maintained compiled knowledge layer: summaries, entities, concepts, comparisons, overview, and synthesis.
- `.cwiki/prompts/` contains generated working prompts. It is not knowledge.
- `wiki/index.md` is the content catalog. Update it after every ingest or saved analysis.
- `wiki/log.md` is append-only. Never rewrite history.

## Required Reading

Before changing wiki content, read `WIKI_SCHEMA.md`.

## Skill Locations

- `.claude/skills/` contains the canonical skill definitions.
- `.agents/skills/` contains compatibility entrypoints for other agents.
- If both exist, prefer `.claude/skills/<skill>/SKILL.md` as the source of truth.

## Operating Principles

- Prefer updating existing wiki pages over creating disconnected pages.
- Save generated knowledge inside the right `wiki/` section, not in a top-level side folder.
- Use `[[slug]]` wikilinks for cross-references.
- Cite source paths or URLs for factual claims.
- Preserve source language during ingest. Chinese sources produce Chinese wiki pages; English sources produce English wiki pages. Do not translate by default unless the user asks.
- Keep contradictions visible until resolved. Do not silently erase uncertainty.
- Valuable query answers should be offered as updates to `wiki/synthesis.md`, `wiki/comparisons/`, or another fitting wiki page.
- Use `cwiki lint .` periodically to find broken links, stale claims, and orphan pages.
