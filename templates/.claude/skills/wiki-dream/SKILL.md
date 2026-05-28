---
name: wiki-dream
description: Use when consolidating Claude, Codex, OpenClaw, Hermes, MEMORY, DREAMS, session transcripts, or logs into implicit experience candidates and promoted wiki lessons.
---

# Wiki Dream

Dreaming extracts reusable operational experience without letting noisy history rewrite the canonical wiki directly.

## Workflow

1. Orient: read `WIKI_SCHEMA.md`, `wiki/index.md`, `wiki/indexes/lessons.md`, and existing `wiki/lessons/`.
2. Gather signal from session transcripts, `MEMORY.md`, `DREAMS.md`, daily logs, or agent logs. Prefer targeted search over reading huge histories.
3. Write raw observations to `.cwiki/experience/observations.jsonl` when possible.
4. Create or update candidate Markdown under `.cwiki/experience/candidates/`.
5. Keep candidates in `status: needs_review` unless the user has explicitly allowed low-risk automatic promotion.
6. Promote only durable, source-traceable, non-duplicate lessons into `wiki/lessons/` or another fitting `wiki/` section.
7. Never auto-promote REM-style hypotheses, personal/sensitive profiling, secrets, or low-confidence one-off guesses.
8. After promotion, run `cwiki ingest-finalize .` so index, graph, hot/stale, backlink, log, and manifest artifacts stay current.

## Candidate Shape

```markdown
---
candidate_id: cand-example
status: needs_review
lesson_type: tool-gotcha
proposed_target: wiki/lessons/example.md
confidence: medium
evidence_count: 2
risk: low
created: YYYY-MM-DD
---

# Candidate: Example

## Proposed Lesson

What future agents should remember.

## Evidence

| Signal | Source | Confidence |
|---|---|---|
| User correction or repeated pattern. | session/log path | high |

## Promotion Check

- [ ] Not a duplicate of existing lessons
- [ ] Has traceable sources
- [ ] Useful beyond one conversation
- [ ] Does not contain secrets or sensitive profiling
- [ ] Proposed target page is correct
```

## Human Review Commands

```bash
cwiki experience list .
cwiki experience promote . .cwiki/experience/candidates/cand-example.md
cwiki experience reject . .cwiki/experience/candidates/cand-example.md --reason "too personal"
```
