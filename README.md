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

## Execution Model

LLM Compound Wiki separates the deterministic local tool layer from the intelligent agent layer.

- The CLI is the scaffold and local utility layer: initialize a wiki, capture sources, rebuild indexes, lint health, search local pages, and generate auditable prompts or briefs.
- The generated wiki folder is the agent workspace. Agents should read `AGENTS.md`, `CLAUDE.md`, `WIKI_SCHEMA.md`, and the local skills before changing `wiki/`.
- The copied skill files are instructions for agents, not executable CLI plugins.
- `ask` and `web-ask` prepare evidence and prompts; they do not call an LLM.
- `answer` calls the `.env` configured model, but only against local wiki retrieval.
- Live web research currently requires a browser-capable agent following `wiki-agent-browser`.

## Repository Layout

```text
.
├── AGENTS.md                 Agent rules for this project
├── bin/cwiki.py              Zero-dependency Python CLI
├── bin/cwiki.mjs             Node/npm compatibility wrapper
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

### 1. Clone

```bash
git clone https://github.com/Forever5471/llm-compound-wiki.git
cd llm-compound-wiki
```

### 2. Create a Wiki

Use the Python CLI directly from the checkout:

```bash
python3 ./bin/cwiki.py init ./my-wiki --domain "AI research notes"
cd my-wiki
python3 ../bin/cwiki.py lint .
```

This creates a wiki with `raw/`, `wiki/`, `.cwiki/prompts/`, `CLAUDE.md`, `AGENTS.md`, `WIKI_SCHEMA.md`, `.env.example`, and workflow skills.

### 3. Add Sources

Put source files under `my-wiki/raw/`, or capture a URL/file:

```bash
python3 ../bin/cwiki.py capture . https://example.com/article --title "Example Article"
python3 ../bin/cwiki.py capture . ./notes.md --title "Project Notes"
python3 ../bin/cwiki.py capture . ./product-plan.docx --title "Product Plan"
python3 ../bin/cwiki.py capture . ./intro-deck.pptx --title "Intro Deck"
python3 ../bin/cwiki.py capture . ./metrics.xlsx --title "Metrics"
```

`capture` writes immutable source records under `raw/captures/` and creates ingest prompts under `.cwiki/prompts/`. It has built-in support for URL records, UTF-8 text/Markdown, OOXML text extraction for `.docx`, `.pptx`, and `.xlsx`, and image file references. For `.pdf`, it uses the local `pdftotext` command when available; otherwise it asks you to convert the PDF to UTF-8 text or route scanned pages through the image/OCR workflow.

For complex formats, use the project's built-in parser skills: `wiki-parse-docx`, `wiki-parse-pdf`, `wiki-parse-image`, `wiki-parse-pptx`, and `wiki-parse-xlsx`. This project does not automatically search GitHub or integrate external parser projects. If the built-in extraction is not good enough, convert the original file to Markdown or UTF-8 text with a tool of your choice, then use this project for capture, ingest, ask, and answer.

Ingest preserves the source language by default: Chinese sources should produce Chinese wiki pages, English sources should produce English wiki pages. Translation only happens when the user explicitly asks for it.

### 4. Ask an Agent to Ingest

Open the generated wiki folder in Codex, Claude Code, OpenCode, Cursor, or another filesystem-capable agent, then ask:

```text
Read CLAUDE.md and WIKI_SCHEMA.md, then process .cwiki/prompts/ingest-xxx.md.
```

The agent should compile the source into:

```text
wiki/
├── overview.md
├── synthesis.md
├── summaries/
├── entities/
├── concepts/
├── comparisons/
├── index.md
└── log.md
```

### 5. Maintain and Search

```bash
python3 ../bin/cwiki.py index .
python3 ../bin/cwiki.py lint .
python3 ../bin/cwiki.py search . "retrieval"
python3 ../bin/cwiki.py ask . "What does this wiki know about retrieval?"
python3 ../bin/cwiki.py web-ask . "What changed recently about this topic?" --wiki-weight 0.6 --web-weight 0.4
OPENAI_API_KEY=... python3 ../bin/cwiki.py answer . "What does this wiki know about retrieval?"
```

## Optional npm Wrapper

If you still want an npm-style command, install from this checkout; the npm entrypoint simply delegates to Python:

```bash
npm install -g .
cwiki init ./my-wiki --domain "Market research"
cwiki search ./my-wiki "pricing"
cwiki lint ./my-wiki
```

The repository keeps a small `bin/cwiki.mjs` Node wrapper for npm compatibility. The actual implementation lives in `bin/cwiki.py`.

Requirements:

- Python 3.10+
- Node/npm only if you want the optional global `cwiki` wrapper

## CLI Commands

```bash
cwiki init <dir> [--domain "..."]
cwiki index <dir>
cwiki lint <dir>
cwiki search <dir> <query>
cwiki ask <dir> <question> [--top-k 6] [--show-context]
cwiki web-ask <dir> <question> [--top-k 6] [--max-web-sources 6] [--wiki-weight 0.6] [--web-weight 0.4] [--no-web] [--show-context]
cwiki answer <dir> <question> [--provider openai|glm] [--model "..."] [--top-k 6]
cwiki capture <dir> <file-or-url> [--title "..."]
```

`capture` does not summarize by itself. It creates a raw-source record and an ingest prompt for your agent. The agent then follows `WIKI_SCHEMA.md` and the skill files to compile the source into the right `wiki/` sections.

`ask` does not call an LLM. It uses hybrid retrieval over the compiled wiki: keyword retrieval for exact matches, lightweight local hash-vector retrieval to reduce synonym and long-document misses, and relationship retrieval over `[[wikilink]]` neighbors. It then writes a model-oriented query prompt under `.cwiki/prompts/` and a human-readable evidence brief under `.cwiki/briefs/`. The brief is useful for quick inspection; hand the prompt to Codex, Claude Code, or another agent for a polished answer.

The lightweight vector retrieval is not an embedding API. It tokenizes local Markdown, hashes tokens into a fixed-size vector, and ranks pages with cosine similarity plus keyword and link-graph boosts. It is zero-dependency and deterministic, but less semantically powerful than model embeddings.

`web-ask` is for questions that need local wiki context plus current web evidence. It first retrieves local wiki pages, then writes three artifacts: `.cwiki/prompts/web-query-*.md` for browser research, `.cwiki/web-research/web-research-*.md` for recording web findings, and `.cwiki/prompts/fusion-*.md` for a later agent to synthesize local wiki evidence with web evidence into the final answer. Default weights are local wiki `0.6` and web search `0.4`; tune them with `--wiki-weight` and `--web-weight`. Use `--web-weight 0` or `--no-web` to disable browsing and produce a local-wiki-only fusion prompt.

The CLI does not browse the live web by itself in the current implementation. The skills copied into `.claude/skills/` and `.agents/skills/` are agent instructions, not executable CLI plugins. Give the generated `web-query-*.md` prompt to a browser-capable agent that can use `wiki-agent-browser`; that agent should search, open sources, write `.cwiki/web-research/*.md`, and then answer from the generated fusion prompt.

A future terminal-only `web-answer` flow could combine wiki retrieval, live web search, configured evidence weights, and the `.env` model provider in one command, but that is not implemented yet.

A browser-capable agent using `wiki-agent-browser` should read the local wiki first, search the web when enabled, open source pages before citing them, and record results under `.cwiki/web-research/`. Final answers should separate local evidence, web evidence, synthesis, and gaps. Every external factual claim needs an exact URL and access date. Durable web sources should be recorded with `cwiki capture . <url> --title "<title>"` before they are ingested into `wiki/`.

`answer` calls a model and writes the draft answer under `.cwiki/answers/`. It currently supports OpenAI's Responses API and GLM through an OpenAI-compatible Chat Completions endpoint. It still creates the same query prompt and human brief first, so answers remain auditable. Draft answers are not written into `wiki/` automatically; review them before asking an agent to preserve useful synthesis in the compiled wiki layer.

## Model Configuration

Each initialized wiki includes `.env.example`. Copy it to a local `.env` in either this project directory or a specific wiki directory. `.env` is ignored by git and is the right place for API keys:

```bash
CWIKI_PROVIDER=glm
CWIKI_GLM_MODEL=glm-4.6v
GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GLM_API_KEY=your-local-key

# Optional OpenAI defaults
CWIKI_OPENAI_MODEL=gpt-5.2
OPENAI_API_KEY=your-local-key

# web-ask defaults
CWIKI_WEB_WIKI_WEIGHT=0.6
CWIKI_WEB_WEIGHT=0.4
CWIKI_WEB_MAX_SOURCES=6
CWIKI_WEB_ENABLED=true
```

Then run:

```bash
python3 ../bin/cwiki.py answer . "How is gray_zone designed?"
```

You can also override the provider and model per command:

```bash
python3 ../bin/cwiki.py answer . "How is gray_zone designed?" --provider glm --model glm-4.6v
```

`web-ask` reads these `.env` defaults. Command-line options take precedence:

```bash
python3 ../bin/cwiki.py web-ask . "Question" --wiki-weight 0.8 --web-weight 0.2
python3 ../bin/cwiki.py web-ask . "Question" --no-web
```

### CLI Config vs Agent Model

The `.env` model settings control terminal/CLI workflows that the project itself runs, such as `cwiki answer`. `cwiki answer` uses the configured provider/model and local wiki retrieval, but it does not perform live web search. The `.env` settings do not change the model selected by Trae, Codex, Claude Code, Cursor, or another agent platform for the current chat.

If you ask an agent to work inside a generated wiki folder, the final prose is usually generated by that agent's active model. The agent should read the wiki's local `CLAUDE.md`, `AGENTS.md`, and `WIKI_SCHEMA.md`, prefer the skills in `.claude/skills/` or `.agents/skills/`, and use those local workflows for capture, ingest, query, update, lint, and browser research. If the local skills do not cover the task, the agent may use its own platform tools or an exploratory implementation while preserving the wiki schema and source-citation rules.

The web evidence weights in `.env` are execution or prompt settings, not a hidden reranker inside the agent. In CLI workflows, `cwiki web-ask` reads them and writes them into the browser research and fusion prompts; it does not execute the browser research itself. In agent workflows, the agent should follow the generated prompt weights or the local wiki instructions when synthesizing local wiki evidence with web evidence.

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

The generated wiki also includes `wiki-init`, `wiki-capture`, `wiki-parse-docx`, `wiki-parse-pdf`, `wiki-parse-image`, `wiki-parse-pptx`, `wiki-parse-xlsx`, `wiki-ingest`, `wiki-query`, `wiki-agent-browser`, `wiki-update`, and `wiki-lint` skills under `.claude/skills/`, plus compatibility entrypoints under `.agents/skills/`.

## Design Principles

- Compiled knowledge beats repeated retrieval.
- Links are part of the knowledge, not decoration.
- The log is append-only, because the wiki's history is also evidence.
- Human judgment directs source selection and emphasis.
- The agent handles bookkeeping, cross-references, and consistency.

## License

MIT
