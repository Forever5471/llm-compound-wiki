# AGENTS.md

This is an LLM Compound Wiki.

## Layer Rules

- `raw/` contains immutable source material. Never edit or delete raw files unless the user explicitly asks.
- `wiki/` contains the AI-maintained compiled knowledge layer: summaries, entities, concepts, comparisons, overview, and synthesis.
- `.cwiki/prompts/` contains generated working prompts. It is not knowledge.
- `.cwiki/graph/` contains generated graph artifacts such as `graph.json` and `graph.md`. It is a reusable navigation artifact, not canonical knowledge.
- `wiki/index.md` is the content catalog. Update it after every ingest or saved analysis.
- `wiki/log.md` is append-only. Never rewrite history.

## Required Reading

Before changing wiki content, read `WIKI_SCHEMA.md`.

## Execution Model

- The CLI is the scaffold and local utility layer: initialize, capture, index, lint, search, and generate prompts or briefs.
- `graph` and `graph-report` create a deterministic graph layer from compiled wiki pages and `[[wikilinks]]`.
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

- `direct`: use direct keyword/vector hits only. Best for narrow fact lookup when one or a few pages clearly answer the question.
- `graph`: start with direct hits, then add inbound/outbound wikilink neighbors from `.cwiki/graph/graph.json`. Best when the question may need nearby concepts, roles, modules, or related entities.
- `path`: use direct hits, graph neighbors, and shortest-path evidence between top hits. Best for workflows, mechanisms, dependencies, relationships, and "how/why" questions.
- `synthesis`: include direct hits, graph context, path evidence, and global overview/synthesis/central pages. Best for comparisons, tradeoffs, strategy, evaluation, or broad summaries.
- `auto`: let the CLI choose a layer from the question. If `auto` selects `path` but no path evidence exists, the CLI falls back to `graph` and records the fallback in Retrieval Trace.

For graph retrieval, first run or refresh `cwiki graph-report .` when links have changed. Then use the query prompt's Retrieval Trace: direct hits are primary evidence, graph-expanded pages are nearby context, path evidence explains relationships, and final context pages define the reproducible evidence pack.

Use `cwiki ask . "<question>" --graph-rerank` or `cwiki answer . "<question>" --graph-rerank` when semantic reranking is worth an extra model call. Inspect the `LLM Graph Rerank` section before answering, but keep source-backed page evidence above rerank reasons.

## Skill Locations

- `.claude/skills/` contains the canonical skill definitions.
- `.agents/skills/` contains compatibility entrypoints for other agents.
- If both exist, prefer `.claude/skills/<skill>/SKILL.md` as the source of truth.
- Use `wiki-capture` before `wiki-ingest` when a source file or URL still needs to be recorded under `raw/captures/`.
- For complex source formats, use the built-in parser skills: `wiki-parse-docx`, `wiki-parse-pdf`, `wiki-parse-image`, `wiki-parse-pptx`, and `wiki-parse-xlsx`.
- For current web research that combines local wiki context with online evidence, use `wiki-agent-browser` and start with `cwiki web-ask . "<question>"`. Use `--web-weight 0` or `--no-web` when web search should be disabled.
- If an answer or evaluation names external-evidence gaps such as missing case studies, metrics, current facts, or migration guidance, run `cwiki eval-answer . <answer-file> --web-on-gaps` or `cwiki answer . "<question>" --web-on-gaps` to create `.cwiki/web-gaps/`, web research, and fusion prompt artifacts.

## Local Configuration

- `.env.example` documents local model and web-search defaults.
- Copy `.env.example` to `.env` before using `cwiki answer` with provider API keys.
- `.env` is ignored by git and should remain local.
- `.env` model settings affect terminal/CLI workflows such as `cwiki answer`; they do not change this agent platform's active chat model.
- `cwiki answer` uses the configured provider/model and local wiki retrieval, but it does not perform live web search.
- `web-ask` reads `.env` defaults for wiki/web evidence weights and source limits, but command-line flags take precedence.
- `web-ask` creates browser research and fusion prompts; it does not execute browser research by itself.
- `--web-on-gaps` uses the same `CWIKI_WEB_*` defaults and supports one-run overrides with `--web-gap-max-sources`, `--web-gap-wiki-weight`, and `--web-gap-web-weight`.
- The skill files in `.claude/skills/` and `.agents/skills/` are agent instructions, not executable CLI plugins.
- When working as an agent inside this wiki, use the current agent model for reasoning and final prose unless the user explicitly asks you to run a CLI command.
- The CLI automatically records model usage for `answer`, graph rerank, and `--llm` evaluation under `.cwiki/usage/llm-usage.jsonl`.
- If this agent platform exposes token or cost numbers for ingest, update, browser research, final answer, or other platform-model work, record them with `cwiki usage-log . --operation <step> --provider agent-platform --model <visible-model-name> ...`.
- Use `cwiki usage-report .` for a full cost report, or filter with `--operation`, `--artifact`, `--question`, `--provider`, `--model`, `--since`, and `--until`.
- For LLM-assisted evaluation inside an agent platform, use the current agent model rather than the `.env` model. Write the assisted assessment to `.cwiki/eval/agent-assisted-*.md`, then attach it with `--agent-eval-file <file> --agent-model <visible-model-name>` so the official report records `provider: agent-platform`.
- Prefer this folder's local instructions and skills before platform-specific skills: read `CLAUDE.md`, `AGENTS.md`, and `WIKI_SCHEMA.md`, then use `.claude/skills/` or `.agents/skills/` for capture, ingest, query, update, lint, and browser research.
- For wiki questions in an agent platform, prefer the hybrid query workflow: use `cwiki ask . "<question>" --retrieval auto` for a stable prompt, evidence brief, and Retrieval Trace, then let the agent inspect additional wiki pages only when the prompt is incomplete.
- If the local skills do not cover the task, use your platform's own tools or an exploratory implementation, while preserving the wiki schema, source-citation rules, and operation log.
- If the user asks for web evidence, run `cwiki web-ask . "<question>"` when useful, read the generated prompts, perform browser research when enabled, and follow the configured weights during synthesis.
- If the user asks about relationships, impact, paths, central concepts, or graph structure, run `cwiki graph-report .`, `cwiki path . <a> <b>`, or `cwiki explain . <slug>` when useful.

## Operating Principles

- Prefer updating existing wiki pages over creating disconnected pages.
- Save generated knowledge inside the right `wiki/` section, not in a top-level side folder.
- Use `[[slug]]` wikilinks for cross-references.
- Cite source paths or URLs for factual claims.
- Preserve source language during ingest. Chinese sources produce Chinese wiki pages; English sources produce English wiki pages. Do not translate by default unless the user asks.
- Keep contradictions visible until resolved. Do not silently erase uncertainty.
- Treat `wiki/overview.md` and `wiki/synthesis.md` as two alternative first reading surfaces, not placeholders. Use `overview.md` for orientation and navigation while the wiki is still accumulating sources; use `synthesis.md` when source-backed pages support an integrated thesis.
- Refresh both `wiki/overview.md` and `wiki/synthesis.md` after every ingest or update. `overview.md` should track the current map and entry links; `synthesis.md` should track the current thesis state, contradictions, evidence inventory, or why no thesis is promoted yet.
- Valuable query answers should be offered as updates to `wiki/synthesis.md`, `wiki/comparisons/`, or another fitting wiki page.
- Web evidence is external until captured. Cite exact URLs and access dates, then use `cwiki capture` before ingesting important web sources into `wiki/`.
- Browser research should be recorded under `.cwiki/web-research/`, then fused with local wiki evidence through the generated `.cwiki/prompts/fusion-*.md`.
- Generated graph artifacts should be refreshed with `cwiki graph-report .` after substantial link or page changes.
- Use `cwiki lint .` periodically to find broken links, stale claims, and orphan pages.
