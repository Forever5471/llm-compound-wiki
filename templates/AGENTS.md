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
- Use `wiki-capture` before `wiki-ingest` when a source file or URL still needs to be recorded under `raw/captures/`.
- For complex source formats, use the built-in parser skills: `wiki-parse-docx`, `wiki-parse-pdf`, `wiki-parse-image`, `wiki-parse-pptx`, and `wiki-parse-xlsx`.
- For current web research that combines local wiki context with online evidence, use `wiki-agent-browser` and start with `cwiki web-ask . "<question>"`. Use `--web-weight 0` or `--no-web` when web search should be disabled.

## Local Configuration

- `.env.example` documents local model and web-search defaults.
- Copy `.env.example` to `.env` before using `cwiki answer` with provider API keys.
- `.env` is ignored by git and should remain local.
- `.env` model settings affect terminal/CLI workflows such as `cwiki answer`; they do not change this agent platform's active chat model.
- `web-ask` reads `.env` defaults for wiki/web evidence weights and source limits, but command-line flags take precedence.
- When working as an agent inside this wiki, use the current agent model for reasoning and final prose unless the user explicitly asks you to run a CLI command.
- Prefer this folder's local instructions and skills before platform-specific skills: read `CLAUDE.md`, `AGENTS.md`, and `WIKI_SCHEMA.md`, then use `.claude/skills/` or `.agents/skills/` for capture, ingest, query, update, lint, and browser research.
- If the local skills do not cover the task, use your platform's own tools or an exploratory implementation, while preserving the wiki schema, source-citation rules, and operation log.
- If the user asks for web evidence, run `cwiki web-ask . "<question>"` when useful, read the generated prompts, perform browser research when enabled, and follow the configured weights during synthesis.

## Operating Principles

- Prefer updating existing wiki pages over creating disconnected pages.
- Save generated knowledge inside the right `wiki/` section, not in a top-level side folder.
- Use `[[slug]]` wikilinks for cross-references.
- Cite source paths or URLs for factual claims.
- Preserve source language during ingest. Chinese sources produce Chinese wiki pages; English sources produce English wiki pages. Do not translate by default unless the user asks.
- Keep contradictions visible until resolved. Do not silently erase uncertainty.
- Valuable query answers should be offered as updates to `wiki/synthesis.md`, `wiki/comparisons/`, or another fitting wiki page.
- Web evidence is external until captured. Cite exact URLs and access dates, then use `cwiki capture` before ingesting important web sources into `wiki/`.
- Browser research should be recorded under `.cwiki/web-research/`, then fused with local wiki evidence through the generated `.cwiki/prompts/fusion-*.md`.
- Use `cwiki lint .` periodically to find broken links, stale claims, and orphan pages.
