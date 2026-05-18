# LLM Usage And Cost Tracking

LLM Compound Wiki keeps a local usage ledger whenever the CLI itself calls a configured model.

## Automatic Records

The CLI appends records to `.cwiki/usage/llm-usage.jsonl` for:

- `cwiki answer`
- `cwiki ask --graph-rerank`
- `cwiki answer --graph-rerank`
- `cwiki eval --llm`
- `cwiki eval-answer --llm`
- `cwiki eval-all --llm`
- scheduled evaluation runs that enable `--llm`

Each record includes operation, provider, model, question or artifact when available, token usage reported by the API, and an estimated cost.

## Cost Rates

The project does not hardcode vendor prices. Configure rates in `.env` as price per 1M tokens:

```bash
CWIKI_COST_INPUT_PER_1M=0
CWIKI_COST_OUTPUT_PER_1M=0
CWIKI_COST_GLM_INPUT_PER_1M=0
CWIKI_COST_GLM_OUTPUT_PER_1M=0
CWIKI_COST_GLM_GLM_4_6V_INPUT_PER_1M=0
CWIKI_COST_GLM_GLM_4_6V_OUTPUT_PER_1M=0
CWIKI_COST_CURRENCY=USD
```

Provider+model rates take precedence over provider rates, and provider rates take precedence over generic rates.

## Reports

Generate a full report:

```bash
cwiki usage-report .
```

Filter to a specific scope:

```bash
cwiki usage-report . --operation answer
cwiki usage-report . --question "gray_zone"
cwiki usage-report . --artifact .cwiki/answers/answer-example.md
cwiki usage-report . --provider glm --model glm-4.6v
cwiki usage-report . --since 2026-05-18 --json
```

## Agent Platform Usage

Agent platforms do not expose their internal token counters to this CLI automatically. When an agent uses its active platform model for ingest, update, browser research, interpretation, or final prose, record the visible usage manually:

```bash
cwiki usage-log . --operation ingest --provider agent-platform --model current-agent-model --input-tokens 12000 --output-tokens 1800 --estimated-cost 0.05 --currency USD --artifact wiki/synthesis.md
```
