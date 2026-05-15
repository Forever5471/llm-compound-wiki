# Evaluation Design

This document describes the evaluation layer for LLM Compound Wiki. Deterministic wiki-quality evaluation is implemented through `cwiki eval <dir>`, deterministic answer-quality evaluation is implemented through `cwiki eval-answer <dir> <answer-file>`, and combined evaluation is implemented through `cwiki eval-all <dir> [--answer <answer-file>] [--wiki-only]`.

The goal is to make a generated wiki auditable after ingestion, and to make generated answers easier to judge for grounding, source use, and protocol compliance.

## Scope

Evaluation should always start with a deterministic local report. It should not require an LLM judge, embedding API, vector database, or live web access.

When the CLI is running on its own and a local `.env` model provider is configured, evaluation may include an additional LLM-assisted assessment via `--llm`. That LLM output must be clearly labeled as LLM-assisted evaluation, and the deterministic non-LLM report must still be printed. Reports must record the provider, model, status, and timestamp used for the LLM-assisted section.

When the wiki is being operated inside an agent platform, the LLM-assisted assessment should use the platform's current agent model, not the project's `.env` model settings. The agent should write its assisted assessment to a Markdown file, then attach it to the official report with `--agent-eval-file <file>` and `--agent-model <label>`. Reports label the model source as `agent-platform` and preserve the source file path.

If no CLI model is configured, output the deterministic structured report and mark the CLI LLM-assisted section as `skipped` when `--llm` was requested.

Evaluation should run only when the user explicitly asks to evaluate wiki quality, answer quality, grounding, source use, or similar quality signals. It should not run automatically after every ingest, ask, web-ask, answer, lint, or index command.

Command status:

```bash
cwiki eval <dir>                              # implemented
cwiki eval-answer <dir> <answer-file>          # implemented
cwiki eval-all <dir> [--answer <answer-file>] [--wiki-only] # implemented
cwiki eval-schedule <dir> --every-days N       # implemented
```

Possible later commands:

```bash
cwiki eval-query <dir> "<question>"
cwiki eval-web-research <dir> <web-research-file>
```

## Design Principles

- Measure what the project can verify locally.
- Run only on explicit evaluation requests; do not make evaluation an implicit side effect of normal wiki workflows.
- Prefer actionable warnings over vague scores.
- Keep evaluation separate from `lint`: `lint` checks structural health; `eval` scores wiki and answer quality.
- Do not pretend to verify factual truth without reading the original source body.
- Treat source traceability, claim hygiene, and answer grounding as first-class quality signals.
- Make reports useful to both humans and agents.
- Never let an LLM-assisted assessment replace the deterministic report.
- Clearly label LLM-assisted output and keep it separate from deterministic findings.

## Wiki Quality Evaluation

`cwiki eval <dir>` should evaluate the compiled `wiki/` layer, not raw sources or prompts.

This mode is useful when the user asks to evaluate wiki quality, ingestion quality, evidence hygiene, maintainability, or readiness for future questions.

Phase 1 writes traceable Markdown reports to `.cwiki/eval/wiki-eval-<timestamp>.md` by default and appends a row to `.cwiki/eval/index.md`. Use `--no-write` to print the report without writing files, or `--output <file>` to choose a report path.

The report language follows the evaluated wiki content. A primarily Chinese wiki should receive a Chinese evaluation report; an English wiki should receive an English report.

Suggested output:

```text
Wiki Quality Report

Overall: 78/100
Structure: 88/100
Evidence: 70/100
Coverage: 74/100
Maintainability: 82/100

Warnings:
- wiki/concepts/retrieval.md has 4 claims without source paths.
- wiki/synthesis.md has no Claim Ledger.
- wiki/entities/openai.md has stale "latest" language; updated 2026-01-02.

Suggested next steps:
- Add source paths to unsourced claims.
- Run cwiki index . after fixing pages.
- Review stale pages before using them for current questions.
```

### Structure Quality

Structure quality checks whether pages follow the wiki schema.

Signals:

- Required root files exist: `WIKI_SCHEMA.md`, `AGENTS.md`, `CLAUDE.md`, `wiki/index.md`, `wiki/log.md`.
- Standard wiki sections exist: `summaries/`, `entities/`, `concepts/`, `comparisons/`.
- Markdown pages have frontmatter.
- Frontmatter includes `title`, `kind`, `tags`, `sources`, `updated`, and `status` where appropriate.
- Filenames are lowercase slugs.
- Pages are placed in a section matching their `kind`.
- `wiki/index.md` references existing pages.
- `wiki/log.md` has append-only style entries.

Potential score:

```text
Structure score = schema compliance + section placement + index/log health
```

### Link Quality

Link quality checks whether the wiki graph is usable.

Signals:

- Broken `[[wikilink]]` count.
- Orphan page count.
- Pages with outbound links.
- Pages with inbound links.
- Overview and synthesis pages link to important topic pages.

This overlaps with `lint`, but `eval` should turn it into an interpretable quality score and prioritized warnings.

### Evidence Quality

Evidence quality checks whether claims are traceable.

Signals:

- Pages that should have a `Claim Ledger` include one.
- Claim ledger rows are parseable Markdown table rows.
- Each claim has a non-empty source.
- Source values point to either:
  - `raw/...`
  - `raw/captures/...`
  - `.cwiki/web-research/...`
  - an exact URL
  - another explicit local evidence path
- Each row includes confidence.
- Each row includes last checked date.
- Page `sources` frontmatter is consistent with claim/source count.
- Pages with factual prose but no claim ledger are flagged.

Recommended severities:

```text
P1: factual claims without any source
P2: claim ledger exists but has missing confidence/date
P3: sources count appears stale
```

### Coverage Quality

Coverage quality estimates whether the wiki has enough compiled knowledge to be useful.

Signals:

- `overview.md` is more than a stub.
- `synthesis.md` is more than a stub.
- Captured sources have corresponding summary pages.
- Important entities/concepts found in summaries have pages or links.
- Comparison pages exist when the wiki contains multiple alternatives, vendors, designs, methods, or decisions.
- The operation log mentions recent ingests and updates.

This is heuristic. The report should avoid claiming the wiki is "complete"; it should say "coverage signals are weak/strong."

### Freshness Quality

Freshness checks whether time-sensitive claims are likely stale.

Signals:

- Pages containing terms like `latest`, `current`, `recent`, `state-of-the-art`, `最新`, `当前`, `近期` with old `updated` dates.
- Claim rows with old `Last checked` values.
- Web-derived sources without access dates.

Default stale threshold:

```text
90 days
```

Possible future flag:

```bash
cwiki eval . --stale-days 30
```

### Maintainability Quality

Maintainability checks whether future agents can safely continue the wiki.

Signals:

- Pages have stable headings.
- Pages include `Open Questions` when uncertainty exists.
- Contradictions are explicit rather than silently resolved.
- Large pages are not too large to inspect comfortably.
- Generated files remain in `.cwiki/`, durable knowledge remains in `wiki/`.

## Answer Quality Evaluation

`cwiki eval-answer <dir> <answer-file>` evaluates a generated answer artifact, usually from `.cwiki/answers/` or a copied Markdown answer.

It does not try to prove whether every statement is true. The deterministic implementation checks whether the answer is grounded, traceable, and compliant with the wiki protocol.

When an answer links to a query prompt generated by `cwiki ask` or `cwiki answer`, answer evaluation also reads the prompt's Retrieval Trace. The report shows the strategy used (`direct`, `graph`, `path`, or `synthesis`), direct-hit usage, graph-expanded page usage, path evidence count, auto fallback reason, and a retrieval quality score. This evaluates whether the retrieval strategy matched the question and whether retrieved context actually supported the final answer.

This mode is useful when the user asks to evaluate answer quality, grounding, source use, or whether a specific response followed wiki/web evidence protocol.

Suggested output:

```text
Answer Quality Report

Overall: 76/100
Grounding: 82/100
Source Use: 70/100
Coverage: 74/100
Protocol: 78/100
Risk: medium

Warnings:
- 3 factual-looking paragraphs have no local citation or URL.
- The answer references web evidence but has no Sources section.
- The answer does not state gaps or uncertainty.
```

### Grounding

Grounding checks whether the answer ties back to wiki evidence.

Signals:

- Contains local citations like `[[slug]]`.
- Cited slugs exist in `wiki/`.
- References source paths such as `raw/...` or URLs.
- If an answer file includes frontmatter metadata, `Relevant Pages` are present and exist.
- The answer does not cite `.cwiki/prompts/` as durable knowledge.

### Source Use

Source use checks whether the answer supports factual claims.

Signals:

- Factual-looking bullet points or paragraphs have nearby citations.
- URL citations are exact links, not vague publisher names.
- Web source citations include access dates when the answer claims web evidence.
- The answer avoids citing search result snippets as sources.
- Local claims refer to wiki pages or claim ledger source paths.

The first version can use heuristics:

- Count paragraphs with numbers, dates, named entities, or strong factual verbs.
- Check whether nearby text includes `[[...]]`, `raw/`, `http://`, or `https://`.
- Flag unsupported paragraphs instead of failing the answer.

### Coverage

Coverage checks whether the answer uses the context it was supposed to use.

Signals:

- If the answer file links to a query prompt, read that prompt and collect its relevant pages.
- The answer cites or discusses at least some top relevant pages.
- If no local pages matched, the answer states that the wiki has insufficient evidence.
- For web-fusion answers, it separates local wiki evidence from web evidence.

### Protocol Compliance

Protocol checks whether the answer follows the expected shape.

For local answers:

- Has a direct answer or synthesis.
- Includes local citations.
- States gaps.
- Does not write changes into `wiki/` unless requested.

For web answers:

- Separates `Local wiki evidence`, `Web evidence`, `Synthesis`, `Gaps`, and `Sources`.
- Includes exact URLs for web facts.
- Includes access dates.
- Calls out conflicts between local wiki and web evidence.

### Risk Signals

Risk signals should be reported even if the score is otherwise high.

Examples:

- Claims live web research was performed, but no web source URLs are present.
- Uses current/recent/latest language without web evidence.
- Cites generated prompts as sources.
- Provides a strong recommendation without citing evidence.
- Omits gaps and uncertainty.
- Web evidence appears in the answer but no `.cwiki/web-research/` file is referenced.

## Combined Quality Evaluation

`cwiki eval-all <dir> [--answer <answer-file>] [--wiki-only]` should generate a combined report when the user explicitly asks for an overall quality assessment.

It should include wiki quality. By default, it scans `.cwiki/answers/` and evaluates the latest `answer-*.md` when one exists. If `--answer` is provided, it evaluates that specific answer instead. If `--wiki-only` is provided or no answer exists, it states that no answer was included and avoids inventing an answer score.

Suggested output:

```text
Combined Evaluation Report

Overall: 77/100
Wiki Quality: 78/100
Answer Quality: 76/100
Risk: medium

Wiki highlights:
- Structure is strong.
- Evidence quality needs source path cleanup.

Answer highlights:
- Answer cites local pages.
- Web evidence is mentioned but sources are incomplete.

Priority fixes:
1. Add source paths to unsourced claim ledger rows.
2. Add Sources and Gaps sections to the answer.
```

If no answer file is found, combined evaluation evaluates wiki quality only and states that no answer was included.

Combined scoring should not hide the underlying category scores. It should always display the wiki and answer components separately.

## Scoring Model

Scores should be simple and explainable.

Initial scoring can use weighted checks:

```text
Wiki overall:
- Structure: 25%
- Link quality: 15%
- Evidence quality: 35%
- Coverage quality: 15%
- Freshness/maintainability: 10%

Answer overall:
- Grounding: 35%
- Source use: 30%
- Coverage: 15%
- Protocol compliance: 15%
- Risk penalties: 5%
```

Combined score when both wiki and answer are evaluated:

```text
Combined overall:
- Wiki quality: 50%
- Answer quality: 50%
```

If only wiki quality is evaluated, the combined report should not invent an answer score.

Scores should never be the only output. Every low score should produce concrete warnings and suggested fixes.

## Report Formats

Initial human-readable format:

```bash
cwiki eval .
cwiki eval-answer . .cwiki/answers/answer-2026-05-11-example.md
```

Evaluation reports should be traceable artifacts. By default, evaluation commands should print the report and write a copy under `.cwiki/eval/`.

Suggested paths:

```text
.cwiki/eval/wiki-eval-YYYY-MM-DD-HHMMSS.md
.cwiki/eval/answer-eval-YYYY-MM-DD-HHMMSS-<answer-slug>.md
.cwiki/eval/combined-eval-YYYY-MM-DD-HHMMSS.md
.cwiki/eval/index.md
```

`.cwiki/eval/` should be ignored by git by default, like prompts, answers, briefs, and web research. Users can copy important reports into `wiki/` only when they intentionally want evaluation findings to become durable wiki knowledge.

Wiki reports and combined reports should expose the same core wiki quality counters so regressions are visible even when the overall score is high:

- total warnings, P1, P2, P3
- broken links
- orphan pages
- missing frontmatter pages
- pages without Claim Ledger
- Claim Ledger rows missing source
- potentially stale pages

Report frontmatter should include:

```yaml
---
title: Wiki Evaluation - 2026-05-11 15:30:00
tags: [evaluation, wiki-quality]
created: 2026-05-11 15:30:00
updated: 2026-05-11
status: final
mode: wiki
llm_assisted: false
target: .
answer_file:
question:
source_file:
raw_capture:
ingest_prompt:
query_prompt:
web_research_file:
operation_log_entry:
overall: 78
---
```

The report must make lineage visible. A reader should be able to tell which day/time the evaluation ran and whether it evaluated:

- the whole wiki,
- a specific raw source ingestion,
- a specific captured source,
- a specific query prompt,
- a specific answer file,
- a specific web research/fusion workflow.

Suggested lineage fields:

```yaml
evaluated_at: 2026-05-11 15:30:00
evaluation_timezone: Asia/Shanghai
mode: answer
target: .
source_file: raw/captures/2026-05-11-example.md
source_title: Example Article
raw_capture: raw/captures/2026-05-11-example.md
ingest_prompt: .cwiki/prompts/ingest-2026-05-11-example.md
question: What does this wiki know about retrieval?
query_prompt: .cwiki/prompts/query-2026-05-11-retrieval.md
answer_file: .cwiki/answers/answer-2026-05-11-153000-retrieval.md
web_research_file: .cwiki/web-research/web-research-2026-05-11-retrieval.md
fusion_prompt: .cwiki/prompts/fusion-2026-05-11-retrieval.md
operation_log_entry: "## [2026-05-11] ingest | Example Article"
```

Fields that do not apply should be left empty, not invented.

`.cwiki/eval/index.md` should list recent evaluation reports, their evaluated time, target, mode, source or answer reference, overall score, and highest severity.

Suggested index columns:

```markdown
| Evaluated At | Mode | Subject | Report | Overall | Highest Severity |
|---|---|---|---|---:|---|
| 2026-05-11 15:30 | answer | `.cwiki/answers/answer-...md` | `answer-eval-...md` | 76 | P1 |
| 2026-05-11 15:35 | wiki | `raw/captures/example.md` ingest impact | `wiki-eval-...md` | 78 | P2 |
```

Suggested flags:

```bash
cwiki eval . --no-write
cwiki eval . --output .cwiki/eval/custom-report.md
cwiki eval-answer . answer.md --output .cwiki/eval/answer-check.md
```

When LLM assistance is available and requested or enabled by the runtime, output should have two sections:

```text
Deterministic Evaluation
...

LLM-Assisted Evaluation
Model: <provider/model or current agent model>
Scope: wiki quality and/or answer quality

...
```

The LLM-assisted section may summarize patterns, prioritize risks, and suggest remediation order. It should not remove deterministic warnings, hide low deterministic scores, or claim factual verification beyond the evidence provided to it.

Implemented JSON output:

```bash
cwiki eval . --json
cwiki eval-answer . .cwiki/answers/answer.md --json
cwiki eval-all . --json
cwiki eval-all . --answer .cwiki/answers/answer.md --json
```

JSON shape:

```json
{
  "deterministic": {
    "mode": "combined",
    "scores": {
      "overall": 82,
      "wiki_quality": 78,
      "answer_quality": 85
    },
    "warnings": []
  },
  "llm_assisted": null
}
```

Future LLM-assisted output should keep the same top-level separation:

```json
{
  "deterministic": {
    "overall": 78,
    "warnings": []
  },
  "llm_assisted": {
    "enabled": true,
    "model": "provider/model-or-agent-model",
    "summary": "..."
  }
}
```

## LLM-Assisted Prompt Contract

When LLM-assisted evaluation is enabled, the LLM should receive a constrained evaluation prompt. It should not receive the entire wiki by default.

Inputs to the LLM:

- evaluation mode: `wiki`, `answer`, or `combined`
- deterministic evaluation report
- relevant warning list with file paths
- small excerpts from affected wiki pages
- answer text when evaluating an answer
- cited page excerpts and source snippets when available
- web research excerpt when the answer explicitly uses web evidence

The LLM should not be asked to re-score everything from scratch. It should interpret the deterministic findings, identify quality risks, prioritize fixes, and call out anything suspicious in the provided excerpts.

The LLM prompt must include these constraints:

- Do not claim to verify factual truth beyond the provided evidence.
- Do not hide or override deterministic warnings.
- Label the output as LLM-assisted evaluation.
- Keep deterministic and LLM-assisted conclusions conceptually separate.
- Prefer concrete file-level remediation steps.
- State uncertainty when evidence is missing.

### Wiki Quality Prompt Template

```text
You are assisting with quality evaluation for an LLM Compound Wiki.

This is an LLM-assisted evaluation. A deterministic non-LLM report has already been produced and must remain the source of record for measurable checks.

Your task:
1. Read the deterministic report.
2. Review the provided wiki page excerpts and warnings.
3. Summarize the most important quality risks.
4. Prioritize concrete remediation steps.
5. Call out uncertainty and missing evidence.

Rules:
- Do not claim you verified factual truth beyond the provided excerpts.
- Do not remove or override deterministic warnings.
- Do not cite files or sources that were not provided.
- Prefer concise, actionable findings with file paths.

Evaluation mode: wiki

Deterministic report:
<deterministic_report>

Relevant warnings:
<warnings>

Wiki excerpts:
<wiki_excerpts>

Return:
- LLM-assisted summary
- Highest priority risks
- Suggested fixes
- Residual uncertainty
```

### Answer Quality Prompt Template

```text
You are assisting with answer quality evaluation for an LLM Compound Wiki.

This is an LLM-assisted evaluation. A deterministic non-LLM report has already been produced and must remain the source of record for measurable checks.

Your task:
1. Read the deterministic report.
2. Review the answer text.
3. Review cited wiki excerpts, source snippets, and web research excerpts when provided.
4. Evaluate whether the answer is grounded, traceable, and protocol-compliant.
5. Prioritize concrete fixes.

Rules:
- Do not claim you verified factual truth beyond the provided evidence.
- Do not remove or override deterministic warnings.
- Do not reward uncited factual claims.
- If the answer claims web evidence but no web sources were provided, flag that risk.
- Prefer concise, actionable findings with file paths or answer sections.

Evaluation mode: answer

Deterministic report:
<deterministic_report>

Answer text:
<answer_text>

Cited wiki excerpts:
<cited_wiki_excerpts>

Source snippets:
<source_snippets>

Web research excerpt:
<web_research_excerpt>

Return:
- LLM-assisted summary
- Grounding risks
- Source-use risks
- Protocol risks
- Suggested fixes
- Residual uncertainty
```

### Combined Quality Prompt Template

```text
You are assisting with combined wiki and answer quality evaluation for an LLM Compound Wiki.

This is an LLM-assisted evaluation. Deterministic non-LLM reports for wiki quality and answer quality have already been produced and must remain the source of record for measurable checks.

Your task:
1. Read both deterministic reports.
2. Review provided wiki excerpts and answer text.
3. Explain how wiki quality affects answer quality.
4. Prioritize fixes across both wiki and answer layers.
5. Identify whether answer issues are caused by weak wiki evidence, poor answer synthesis, or both.

Rules:
- Do not claim you verified factual truth beyond the provided evidence.
- Do not remove or override deterministic warnings.
- Keep wiki-layer and answer-layer findings distinct.
- Prefer concrete remediation steps.

Evaluation mode: combined

Wiki deterministic report:
<wiki_deterministic_report>

Answer deterministic report:
<answer_deterministic_report>

Wiki excerpts:
<wiki_excerpts>

Answer text:
<answer_text>

Source/web excerpts:
<source_and_web_excerpts>

Return:
- LLM-assisted summary
- Wiki-layer risks
- Answer-layer risks
- Cross-layer diagnosis
- Priority fixes
- Residual uncertainty
```

### Prompt Size Control

The implementation should bound LLM prompt size.

Recommended defaults:

- Include all P1 warnings.
- Include up to 10 P2 warnings.
- Include up to 5 affected wiki page excerpts.
- Limit each excerpt to roughly 1,500 characters.
- Include the full answer text if it is short; otherwise include the answer frontmatter, headings, cited sections, and unsupported paragraphs.
- Prefer cited pages and pages with deterministic warnings.

If the prompt has to truncate content, the LLM-assisted output must mention that it reviewed excerpts, not the full wiki.

## Relationship To Existing Commands

`cwiki lint` should remain a health checker. It answers: "Is the wiki structurally broken?"

`cwiki eval` should answer: "How trustworthy and maintainable is this wiki?"

`cwiki ask` and `cwiki web-ask` generate prompts and briefs.

`cwiki eval-answer` evaluates whether a generated answer used those prompts and sources responsibly.

`cwiki eval-all` combines wiki quality and answer quality into one report when the user asks for an overall assessment.

Neither `eval` nor `eval-answer` should be triggered implicitly by `ingest`, `ask`, `web-ask`, `answer`, `index`, or `lint`. Agents may suggest running evaluation when quality risk is visible, but they should wait for explicit user instruction before doing so.

Evaluation reports belong in `.cwiki/eval/` by default. They are audit artifacts, not durable wiki knowledge unless the user explicitly asks to preserve their conclusions in `wiki/`.

## Implementation Phases

### Phase 1: Deterministic Wiki Evaluation

Implement:

```bash
cwiki eval <dir>
```

Checks:

- structure quality
- broken links and orphan pages
- claim ledger presence and row completeness
- stale-current-language warnings
- index/log presence
- write report to `.cwiki/eval/` by default
- maintain `.cwiki/eval/index.md`
- include evaluated timestamp and source/ingest lineage when evaluation is scoped to a source or recent ingest

No model calls.

### Phase 2: Deterministic Answer Evaluation

Implement:

```bash
cwiki eval-answer <dir> <answer-file>
```

Checks:

- local citations exist and resolve
- source paths or URLs appear near factual claims
- gaps/uncertainty section exists
- web-answer protocol sections exist when web evidence is used
- generated prompts are not treated as durable evidence
- write report to `.cwiki/eval/` by default
- link answer file and related prompt/research files when available
- include evaluated timestamp, question, answer file, query prompt, and web research/fusion references when available

No model calls.

### Phase 3: Combined Evaluation Report

Implemented:

```bash
cwiki eval-all <dir> [--answer <answer-file>] [--wiki-only]
```

Behavior:

- Run wiki evaluation.
- Run answer evaluation against `--answer` when provided; otherwise auto-select the latest `.cwiki/answers/answer-*.md` when available.
- Skip answer evaluation only when `--wiki-only` is provided or no answer exists.
- Print separate category scores plus a combined score when both are available.
- Keep warnings traceable to wiki files or answer files.

No model calls.

### Phase 4: Optional JSON Output

Implemented:

```bash
--json
```

This enables CI and agent automation.

### Phase 5: LLM-Assisted Assessment

Implemented as an optional LLM-assisted assessment path.

```bash
cwiki eval . --llm
cwiki eval-answer . answer.md --llm
cwiki eval-all . --answer answer.md --llm
```

For agent-platform assisted evaluation:

```bash
cwiki eval-answer . answer.md --agent-eval-file .cwiki/eval/agent-assisted-eval.md --agent-model "current-agent-model"
cwiki eval-all . --answer answer.md --agent-eval-file .cwiki/eval/agent-assisted-eval.md --agent-model "current-agent-model"
```

Behavior:

- Always run deterministic evaluation first.
- If `.env` config provides a model and API key, the CLI can call that model for the LLM-assisted section.
- If evaluation is being handled by an agent platform, use the current agent model for the LLM-assisted section instead of calling the project's `.env` model, then attach it with `--agent-eval-file`.
- If no model key is available, keep deterministic output and mark LLM-assisted evaluation as `skipped`.
- Clearly label the LLM-assisted section.
- Record provider, model, status, and timestamp in the report.
- Feed the LLM only the deterministic report, cited pages, answer text, and necessary snippets by default, not the entire wiki.
- Treat the LLM output as interpretive guidance, not as the source of truth.

### Phase 6: Scheduled Combined Evaluation

Implemented as local wiki configuration:

```bash
cwiki eval-schedule . --every-days 7 --llm
cwiki eval-schedule . --run-if-due
```

The schedule is stored under `.cwiki/eval/schedule.json`. It does not create an operating-system timer by itself; users can call `--run-if-due` from cron, Task Scheduler, CI, or an agent platform automation. For agent-platform automations, prefer deterministic CLI eval plus an agent-written LLM-assisted section using the active platform model; use `--llm` only when the CLI should call the local `.env` model.

## Open Questions

- Should `wiki/synthesis.md` always require a Claim Ledger, or can it cite through linked pages?
- Should eval fail with a non-zero exit code below a configurable threshold?
- Should answer evaluation support plain text answers, or only `.cwiki/answers/*.md` files?
- Should `.cwiki/eval/index.md` keep all historical reports, or only the most recent N reports?
- What stale threshold should be default for fast-moving domains?

## Recommended Defaults

- Print human-readable reports by default.
- Write report files under `.cwiki/eval/` by default, and support `--no-write` for terminal-only output.
- Exit `0` unless there are P1 issues or `--fail-under <score>` is set.
- Keep LLM-assisted assessment out of the first implementation phase, but design reports so it can be added without replacing deterministic output.
- Prefer warnings with file paths over abstract quality labels.
- Do not run evaluation automatically as part of normal commands; require an explicit `cwiki eval` or `cwiki eval-answer` request.
- Support separate wiki and answer evaluation, and a combined report when the user explicitly asks for overall quality.
- When LLM assistance is used, print both deterministic and LLM-assisted sections.
- Keep `.cwiki/eval/` ignored by git unless the user intentionally changes that policy.
