# LLM 用量与成本统计

当 CLI 自己调用用户配置的大模型时，LLM Compound Wiki 会写入本地用量台账。

## 自动记录范围

这些命令会自动追加记录到 `.cwiki/usage/llm-usage.jsonl`：

- `cwiki answer`
- `cwiki ask --graph-rerank`
- `cwiki answer --graph-rerank`
- `cwiki eval --llm`
- `cwiki eval-answer --llm`
- `cwiki eval-all --llm`
- 开启 `--llm` 的 scheduled eval

每条记录会包含 operation、provider、model、问题或产物路径、API 返回的 token usage，以及估算成本。

## 成本单价

项目不会写死供应商价格。请在 `.env` 中配置每 100 万 token 的价格：

```bash
CWIKI_COST_INPUT_PER_1M=0
CWIKI_COST_OUTPUT_PER_1M=0
CWIKI_COST_GLM_INPUT_PER_1M=0
CWIKI_COST_GLM_OUTPUT_PER_1M=0
CWIKI_COST_GLM_GLM_4_6V_INPUT_PER_1M=0
CWIKI_COST_GLM_GLM_4_6V_OUTPUT_PER_1M=0
CWIKI_COST_CURRENCY=USD
```

优先级是 provider+model 单价高于 provider 单价，provider 单价高于通用单价。

## 生成报告

完整报告：

```bash
cwiki usage-report .
```

按范围过滤：

```bash
cwiki usage-report . --operation answer
cwiki usage-report . --question "gray_zone"
cwiki usage-report . --artifact .cwiki/answers/answer-example.md
cwiki usage-report . --provider glm --model glm-4.6v
cwiki usage-report . --since 2026-05-18 --json
```

## Agent 平台用量

agent 平台不会自动把内部 token 计数暴露给 CLI。当 agent 使用当前平台模型做 ingest、update、浏览器研究、解释判断或最终回答时，如果平台界面能看到 token 或费用，需要手动补记：

```bash
cwiki usage-log . --operation ingest --provider agent-platform --model current-agent-model --input-tokens 12000 --output-tokens 1800 --estimated-cost 0.05 --currency USD --artifact wiki/synthesis.md
```
