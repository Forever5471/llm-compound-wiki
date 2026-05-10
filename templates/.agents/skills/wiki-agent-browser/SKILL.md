---
name: wiki-agent-browser
description: Use when a wiki question needs current web evidence, live articles, market data, standards, releases, regulations, or any source outside the local wiki.
---

# Wiki Agent Browser

Use the canonical instructions at `.claude/skills/wiki-agent-browser/SKILL.md`.

Summary:

1. Run `cwiki web-ask . "<question>"` if no web query prompt exists. Use `--web-weight 0` or `--no-web` to disable browsing.
2. Read the generated `.cwiki/prompts/web-query-*.md`.
3. Read local wiki context first.
4. Search and open web sources; never cite search snippets.
5. Write browser findings into `.cwiki/web-research/web-research-*.md`.
6. Read `.cwiki/prompts/fusion-*.md` to produce the final answer.
7. Respect evidence weights from the prompt: local wiki and web search may have different weights.
8. Answer with separate local evidence, web evidence, synthesis, gaps, and sources.
9. Cite local pages as `[[slug]]` and external facts with exact URLs plus access dates.
10. Capture durable web sources with `cwiki capture . <url> --title "<title>"` before ingesting them into `wiki/`.
