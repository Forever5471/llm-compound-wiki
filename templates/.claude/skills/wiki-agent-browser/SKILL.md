---
name: wiki-agent-browser
description: Use when a wiki question needs current web evidence, live articles, market data, standards, releases, regulations, or any source outside the local wiki.
---

# Wiki Agent Browser

This skill combines the compiled local wiki with traceable web research. The local wiki remains the durable knowledge layer; web results are external evidence until they are captured and ingested.

## Trigger

Use this skill when:

- the user asks for latest, current, recent, today, market, pricing, data, policy, regulation, release, benchmark, or news
- the local wiki is likely stale or incomplete
- the user explicitly asks to search, browse, verify online, or combine web sources with wiki knowledge

## Steps

1. Run `cwiki web-ask . "<question>"` if a web query prompt has not already been created.
   - Default evidence weights are local wiki `0.6` and web search `0.4`.
   - Wiki-level defaults can be set in `.env` with `CWIKI_WEB_WIKI_WEIGHT`, `CWIKI_WEB_WEIGHT`, `CWIKI_WEB_MAX_SOURCES`, and `CWIKI_WEB_ENABLED`.
   - Use `--wiki-weight <number>` and `--web-weight <number>` to tune synthesis behavior.
   - Use `--web-weight 0` or `--no-web` to disable browsing and produce a local-wiki-only fusion prompt.
2. Read the generated `.cwiki/prompts/web-query-*.md`.
3. Read `WIKI_SCHEMA.md`, `wiki/index.md`, and the relevant local wiki pages in full.
4. Search the web with focused queries derived from the question and local page titles.
5. Open each candidate source and inspect the actual source page. Do not cite search result snippets.
6. Prefer primary and durable sources:
   - official documentation, product pages, standards, filings, release notes
   - papers, reports, datasets, or reputable data providers
   - reputable journalism only when primary sources are unavailable
7. Keep source notes with title, URL, publisher or author, publication date when visible, and access date.
8. Write browser findings into `.cwiki/web-research/web-research-*.md`.
9. Update `.cwiki/web-captures/web-captures-*.md` with durable-source decisions.
10. Read the generated `.cwiki/prompts/fusion-*.md`.
11. Answer with clear sections:
   - Local wiki evidence
   - Web evidence
   - Synthesis
   - Gaps and uncertainty
   - Sources
12. Cite local evidence with `[[slug]]` and source paths from claim ledgers.
13. Cite web evidence with Markdown links to the exact URLs used.
14. If the agent platform shows token or cost numbers for browser research or synthesis, record them with `cwiki usage-log . --operation web-research --provider agent-platform --model <visible-model-name> ...`.

## Evidence Weights

Weights are synthesis guidance, not mathematical truth.

- Higher local wiki weight means the compiled wiki is the baseline and web evidence mainly verifies, updates, or challenges it.
- Higher web weight means current external evidence can override stale local claims, but conflicts must be explicit.
- Equal weights mean reconcile both layers carefully.
- Web weight `0` or `--no-web` means do not browse; answer only from local wiki context and state that web evidence was disabled.

## Persistence

If web evidence should become durable wiki knowledge:

1. Run `cwiki capture . <url> --title "<title>"` for each important web source.
2. Mark the source in `.cwiki/web-captures/web-captures-*.md` with the captured raw path.
3. Process the generated `.cwiki/prompts/ingest-*.md` with `wiki-ingest`.
4. Preserve source language unless the user asks for translation.
5. Update affected wiki pages with source-backed claim ledger rows.
6. Run `cwiki index .`.
7. Append to `wiki/log.md`.

## Rules

- Do not silently replace local wiki conclusions with web results; call out conflicts.
- Do not cite URLs you did not open.
- Do not cite sources that only aggregate or scrape content if a primary source is available.
- Every external factual claim needs a URL.
- Record the access date for web evidence.
- Keep `.cwiki/web-research/*.md` as the auditable browser research artifact for the final answer.
- Keep `.cwiki/web-captures/*.md` as the handoff for durable source capture.
- If a site is inaccessible, paywalled, or ambiguous, say so and choose another source.
