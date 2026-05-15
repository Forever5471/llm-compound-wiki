# Evaluation 设计

本文档描述 LLM Compound Wiki 的评价能力。确定性的 wiki 质量评价已经通过 `cwiki eval <dir>` 实现，确定性的问答质量评价已经通过 `cwiki eval-answer <dir> <answer-file>` 实现；综合评价已经通过 `cwiki eval-all <dir> [--answer <answer-file>] [--wiki-only]` 实现。

目标是让生成后的 wiki 在摄入后可审计，也让生成后的答案更容易从 grounding、来源使用和协议遵守情况上进行判断。

## 范围

评价能力必须始终先生成确定性的本地报告。第一版不依赖 LLM judge、embedding API、向量数据库或实时联网能力。

当 CLI 独立运行且本地 `.env` 已配置模型 provider 时，evaluation 可以通过 `--llm` 额外包含一段 LLM 参与的评估结论。该部分必须明确标注为 LLM-assisted evaluation，同时仍然输出无 LLM 参与的确定性报告。

当 wiki 正在 agent 平台中操作时，LLM-assisted assessment 应使用该平台当前 agent 模型，而不是项目 `.env` 里的模型配置。agent 应先把辅助评估写成 Markdown 文件，再用 `--agent-eval-file <file>` 和 `--agent-model <label>` 附加进正式报告。报告会把模型来源标为 `agent-platform`，记录模型名称和辅助评估来源文件。

如果没有 CLI 模型配置，则仍输出确定性的结构化报告；当用户请求了 CLI `--llm` 时，将 LLM-assisted 部分标记为 `skipped`。

只有当用户明确要求评估 wiki 质量、问答质量、grounding、来源使用或类似质量信号时，才应执行 evaluation。它不应在每次 ingest、ask、web-ask、answer、lint 或 index 后自动运行。

命令状态：

```bash
cwiki eval <dir>                              # 已实现
cwiki eval-answer <dir> <answer-file>          # 已实现
cwiki eval-all <dir> [--answer <answer-file>] [--wiki-only] # 已实现
```

未来可选命令：

```bash
cwiki eval-query <dir> "<question>"
cwiki eval-web-research <dir> <web-research-file>
```

## 设计原则

- 只评价项目能在本地可靠验证的内容。
- 只在明确的质量评估请求下运行；不要把 evaluation 变成普通 wiki 工作流的隐式副作用。
- 优先输出可操作的 warning，而不是抽象的分数。
- 和 `lint` 分工清楚：`lint` 检查结构健康，`eval` 评价 wiki 和答案质量。
- 不在没有读取原始来源正文的情况下假装验证事实真伪。
- 把来源可追踪性、claim 卫生和答案 grounding 当作核心质量信号。
- 报告要同时方便人读，也方便 agent 后续执行修复。
- 不允许 LLM-assisted assessment 替代确定性报告。
- LLM 参与的输出必须单独标注，并和确定性发现分开。

## Wiki 质量评价

`cwiki eval <dir>` 应评价已经编译好的 `wiki/` 层，而不是 `raw/` 来源或 `.cwiki/prompts/` 工作提示。

当用户要求评估 wiki 质量、摄入质量、证据卫生、可维护性或后续问答准备度时，应使用该模式。

第一阶段默认把可追溯的 Markdown 报告写入 `.cwiki/eval/wiki-eval-<timestamp>.md`，并向 `.cwiki/eval/index.md` 追加一条索引记录。可以用 `--no-write` 只打印报告而不写文件，也可以用 `--output <file>` 指定报告路径。

评估报告的语言应跟随被评估 wiki 的主要内容语言。以中文为主的 wiki 应输出中文评估报告；以英文为主的 wiki 应输出英文评估报告。

建议输出：

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

### 结构质量

结构质量检查页面是否遵守 wiki schema。

信号：

- 必要根文件存在：`WIKI_SCHEMA.md`、`AGENTS.md`、`CLAUDE.md`、`wiki/index.md`、`wiki/log.md`。
- 标准 wiki 分区存在：`summaries/`、`entities/`、`concepts/`、`comparisons/`。
- Markdown 页面有 frontmatter。
- frontmatter 包含适当字段：`title`、`kind`、`tags`、`sources`、`updated`、`status`。
- 文件名是小写 slug。
- 页面所在分区和 `kind` 大体匹配。
- `wiki/index.md` 引用的页面真实存在。
- `wiki/log.md` 保持追加式操作日志风格。

可能的评分方式：

```text
Structure score = schema compliance + section placement + index/log health
```

### 链接质量

链接质量检查 wiki 图谱是否可用。

信号：

- 断掉的 `[[wikilink]]` 数量。
- 孤立页面数量。
- 有出链的页面数量。
- 有入链的页面数量。
- `overview.md` 和 `synthesis.md` 是否链接到重要主题页。

这一部分和 `lint` 有重叠，但 `eval` 应把它转换成更容易理解的质量分数和优先级 warning。

### 证据质量

证据质量检查 claim 是否可追踪。

信号：

- 应该有 `Claim Ledger` 的页面包含该部分。
- Claim Ledger 行能被解析成 Markdown 表格行。
- 每条 claim 有非空 source。
- source 指向以下之一：
  - `raw/...`
  - `raw/captures/...`
  - `.cwiki/web-research/...`
  - 精确 URL
  - 其他明确的本地证据路径
- 每行包含 confidence。
- 每行包含 last checked 日期。
- 页面 frontmatter 中的 `sources` 数量和 claim/source 数量大体一致。
- 有事实性正文但没有 Claim Ledger 的页面被标记。

建议严重程度：

```text
P1: factual claims without any source
P2: claim ledger exists but has missing confidence/date
P3: sources count appears stale
```

### 覆盖质量

覆盖质量估计 wiki 是否已经有足够的编译知识可用。

信号：

- `overview.md` 不是空壳。
- `synthesis.md` 不是空壳。
- 已捕获来源有对应 summary 页面。
- summary 中出现的重要实体/概念有页面或链接。
- 当 wiki 中存在多个方案、供应商、设计、方法或决策时，有 comparison 页面。
- 操作日志记录了近期 ingest 和 update。

这部分是启发式评价。报告不应声称 wiki “完整”，而应表达为“coverage signals are weak/strong”。

### 时效质量

时效质量检查时间敏感 claim 是否可能过期。

信号：

- 页面包含 `latest`、`current`、`recent`、`state-of-the-art`、`最新`、`当前`、`近期` 等词，但 `updated` 日期较旧。
- Claim Ledger 行的 `Last checked` 较旧。
- 来自 web 的来源没有 access date。

默认过期阈值：

```text
90 days
```

未来可选参数：

```bash
cwiki eval . --stale-days 30
```

### 可维护性质量

可维护性质量检查后续 agent 是否能安全继续维护 wiki。

信号：

- 页面有稳定标题结构。
- 存在不确定性时包含 `Open Questions`。
- 矛盾被显式保留，而不是静默覆盖。
- 页面不过大，便于 agent 阅读。
- 临时生成文件留在 `.cwiki/`，长期知识沉淀在 `wiki/`。

## 问答质量评价

`cwiki eval-answer <dir> <answer-file>` 评价一个生成后的答案文件，通常来自 `.cwiki/answers/`，也可以是复制进来的 Markdown 答案。

它不应试图证明每句话都是真的。确定性实现会检查答案是否 grounded、可追踪、并遵守 wiki 协议。

当答案链接到 `cwiki ask` 或 `cwiki answer` 生成的 query prompt 时，answer evaluation 还会读取 prompt 中的 Retrieval Trace。报告会展示本次使用的检索策略（`direct`、`graph`、`path` 或 `synthesis`）、直接命中页面使用情况、图谱扩展页面使用情况、路径证据数量、auto 回退原因和检索质量分数。这个维度用于判断检索策略是否匹配问题复杂度，以及被检索出的上下文是否真的支撑了最终回答。

当用户要求评估答案质量、grounding、来源使用，或某个回答是否遵守 wiki/web evidence 协议时，应使用该模式。

建议输出：

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

Grounding 检查答案是否回到 wiki 证据。

信号：

- 包含本地引用，例如 `[[slug]]`。
- 被引用的 slug 在 `wiki/` 中真实存在。
- 引用了 source path，例如 `raw/...`，或 URL。
- 如果 answer 文件包含 frontmatter 元数据，则有 `Relevant Pages`，且页面存在。
- 答案没有把 `.cwiki/prompts/` 当作长期知识来源引用。

### 来源使用

来源使用检查答案是否用证据支撑事实性表达。

信号：

- 事实性 bullet 或段落附近有引用。
- URL 引用是精确链接，而不是模糊的发布方名称。
- 如果答案声称使用了 web evidence，URL 附近有 access date。
- 答案不把搜索结果摘要当作来源。
- 本地 claim 引用 wiki 页面或 Claim Ledger 中的 source path。

第一版可以使用启发式：

- 统计包含数字、日期、命名实体或强事实动词的段落。
- 检查附近是否包含 `[[...]]`、`raw/`、`http://` 或 `https://`。
- 标记未支撑段落，而不是直接判定答案失败。

### 覆盖度

覆盖度检查答案是否使用了它应该使用的上下文。

信号：

- 如果 answer 文件链接到 query prompt，读取该 prompt 并收集 relevant pages。
- 答案引用或讨论了部分 top relevant pages。
- 如果没有本地页面命中，答案明确说明 wiki 证据不足。
- 对 web-fusion answer，本地 wiki 证据和 web evidence 有分层。

### 协议遵守

协议遵守检查答案是否符合预期结构。

本地答案：

- 有直接回答或 synthesis。
- 包含本地引用。
- 说明 gaps。
- 除非用户要求，否则不写入 `wiki/`。

联网答案：

- 分开 `Local wiki evidence`、`Web evidence`、`Synthesis`、`Gaps`、`Sources`。
- web facts 有精确 URL。
- 包含 access dates。
- 本地 wiki 和 web evidence 冲突时明确指出。

### 风险信号

即使分数不低，风险信号也应单独报告。

例子：

- 声称做了实时联网研究，但没有任何 web source URL。
- 使用 current/recent/latest 语言，但没有 web evidence。
- 把生成的 prompt 当作来源。
- 给出强建议但没有引用证据。
- 没有说明 gaps 和 uncertainty。
- 答案包含 web evidence，但没有引用 `.cwiki/web-research/` 文件。

## 综合质量评价

`cwiki eval-all <dir> [--answer <answer-file>] [--wiki-only]` 应在用户明确要求整体质量评估时生成综合报告。

它应包含 wiki 质量。默认情况下，它会扫描 `.cwiki/answers/` 并选择最新的 `answer-*.md` 进行问答质量评估；如果提供 `--answer`，则评估指定 answer；如果提供 `--wiki-only` 或当前没有 answer 文件，则说明本次没有包含 answer，且不虚构问答质量分数。

建议输出：

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

如果没有找到 answer 文件，综合评价只评价 wiki 质量，并说明本次没有包含 answer。

综合评分不应隐藏底层分类分数。报告中应始终分别展示 wiki 和 answer 的组成分数。

## 评分模型

评分应简单、可解释。

初始版本可以使用加权检查：

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

当同时评价 wiki 和 answer 时，综合分数可以先采用：

```text
Combined overall:
- Wiki quality: 50%
- Answer quality: 50%
```

如果只评价 wiki 质量，综合报告不应虚构 answer 分数。

分数不能是唯一输出。每个低分都应对应具体 warning 和建议修复步骤。

## 报告格式

初始人类可读格式：

```bash
cwiki eval .
cwiki eval-answer . .cwiki/answers/answer-2026-05-11-example.md
```

评估报告应成为可追踪工件。默认情况下，evaluation 命令应在终端打印报告，同时把一份副本写入 `.cwiki/eval/`。

建议路径：

```text
.cwiki/eval/wiki-eval-YYYY-MM-DD-HHMMSS.md
.cwiki/eval/answer-eval-YYYY-MM-DD-HHMMSS-<answer-slug>.md
.cwiki/eval/combined-eval-YYYY-MM-DD-HHMMSS.md
.cwiki/eval/index.md
```

`.cwiki/eval/` 默认应和 prompts、answers、briefs、web research 一样被 git 忽略。只有当用户明确希望把某次评估结论沉淀为长期知识时，才应把重要报告内容复制或总结进 `wiki/`。

Wiki 报告和综合报告都应暴露同一组核心 wiki 质量计数，这样即使总分较高，也能看出是否发生结构退化：

- 警告总数、P1、P2、P3
- 断链数
- 孤立页面数
- 缺少 frontmatter 的页面数
- 缺少 Claim Ledger 的页面数
- 缺少 source 的 Claim 行数
- 可能过期的页面数

报告 frontmatter 建议包含：

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

报告必须能看出 lineage。读者应能判断这份评估是在什么日期/时间运行的，以及它评价的是：

- 整个 wiki，
- 某个原始文件摄入，
- 某个 captured source，
- 某个 query prompt，
- 某个 answer 文件，
- 某次 web research/fusion 工作流。

建议 lineage 字段：

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

不适用的字段应留空，不要编造。

`.cwiki/eval/index.md` 应列出近期 evaluation 报告、评估时间、目标、模式、source 或 answer 引用、整体分数和最高严重程度。

建议 index 列：

```markdown
| Evaluated At | Mode | Subject | Report | Overall | Highest Severity |
|---|---|---|---|---:|---|
| 2026-05-11 15:30 | answer | `.cwiki/answers/answer-...md` | `answer-eval-...md` | 76 | P1 |
| 2026-05-11 15:35 | wiki | `raw/captures/example.md` ingest impact | `wiki-eval-...md` | 78 | P2 |
```

建议参数：

```bash
cwiki eval . --no-write
cwiki eval . --output .cwiki/eval/custom-report.md
cwiki eval-answer . answer.md --output .cwiki/eval/answer-check.md
```

当存在可用模型并启用或由运行环境提供 LLM 参与时，输出应包含两个部分：

```text
Deterministic Evaluation
...

LLM-Assisted Evaluation
Model: <provider/model or current agent model>
Scope: wiki quality and/or answer quality

...
```

LLM-assisted 部分可以总结模式、排序风险、建议修复优先级。它不能删除确定性 warning，不能隐藏确定性低分，也不能声称自己完成了超出输入证据范围的事实验证。

已实现 JSON 输出：

```bash
cwiki eval . --json
cwiki eval-answer . .cwiki/answers/answer.md --json
cwiki eval-all . --json
cwiki eval-all . --answer .cwiki/answers/answer.md --json
```

JSON 结构：

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

未来 LLM-assisted 输出应保持相同的顶层分离：

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

## LLM 辅助评估 Prompt 约定

当启用 LLM-assisted evaluation 时，LLM 应收到受约束的评估 prompt。默认不应把整个 wiki 直接交给 LLM。

提供给 LLM 的输入：

- evaluation mode：`wiki`、`answer` 或 `combined`
- deterministic evaluation report
- 带文件路径的 warning 列表
- 受影响 wiki 页面的少量摘录
- 评估答案时的 answer text
- 可用的被引用页面摘录和 source snippets
- 当答案明确使用 web evidence 时，提供 web research excerpt

LLM 不应被要求从零重新打分。它应解释 deterministic findings，识别质量风险，排序修复优先级，并指出提供摘录中可见的可疑点。

LLM prompt 必须包含这些约束：

- 不要声称验证了超出输入证据范围的事实真伪。
- 不要隐藏或覆盖 deterministic warnings。
- 明确标注输出是 LLM-assisted evaluation。
- 概念上区分 deterministic 结论和 LLM-assisted 结论。
- 优先给出具体到文件的修复建议。
- 证据不足时说明不确定性。

### Wiki 质量 Prompt 模板

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

### 问答质量 Prompt 模板

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

### 综合质量 Prompt 模板

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

### Prompt 大小控制

实现时应限制 LLM prompt 大小。

建议默认值：

- 包含全部 P1 warnings。
- 最多包含 10 条 P2 warnings。
- 最多包含 5 个受影响 wiki 页面摘录。
- 每段摘录限制在约 1,500 字符。
- 如果答案较短，包含完整 answer text；否则只包含 answer frontmatter、标题结构、被引用段落和未支撑段落。
- 优先选择被引用页面和带 deterministic warnings 的页面。

如果 prompt 必须截断内容，LLM-assisted 输出必须说明它评估的是摘录，不是整个 wiki。

## 和现有命令的关系

`cwiki lint` 继续作为健康检查器。它回答：“这个 wiki 结构上有没有坏？”

`cwiki eval` 回答：“这个 wiki 有多可信、多可维护？”

`cwiki ask` 和 `cwiki web-ask` 生成 prompt 和 brief。

`cwiki eval-answer` 评价生成后的答案是否负责任地使用了这些 prompt 和来源。

`cwiki eval-all` 在用户要求整体质量评估时，把 wiki 质量和问答质量合并到一份报告里。

`eval` 和 `eval-answer` 都不应被 `ingest`、`ask`、`web-ask`、`answer`、`index` 或 `lint` 隐式触发。agent 可以在发现明显质量风险时建议用户运行 evaluation，但应等待用户明确指令后再执行。

Evaluation 报告默认属于 `.cwiki/eval/`。它们是审计工件，不是长期 wiki 知识；除非用户明确要求，否则不应把评估结论写进 `wiki/`。

## 实现阶段

### Phase 1：确定性 Wiki 评价

已实现：

```bash
cwiki eval <dir>
```

检查：

- 结构质量
- broken links 和 orphan pages
- Claim Ledger 是否存在、行是否完整
- stale-current-language warnings
- index/log 是否存在
- 默认把报告写入 `.cwiki/eval/`
- 维护 `.cwiki/eval/index.md`
- 当评估范围关联某个 source 或近期 ingest 时，记录评估时间和 source/ingest lineage

不调用模型。

### Phase 2：确定性答案评价

已实现：

```bash
cwiki eval-answer <dir> <answer-file>
```

检查：

- 本地引用存在且能解析
- source paths 或 URLs 出现在事实性 claim 附近
- gaps/uncertainty section 存在
- 使用 web evidence 时，有 web-answer 协议结构
- 生成的 prompts 没有被当作长期证据
- 默认把报告写入 `.cwiki/eval/`
- 可用时链接 answer 文件和相关 prompt/research 文件
- 可用时记录评估时间、question、answer file、query prompt、web research/fusion 引用

不调用模型。

### Phase 3：综合评价报告

已实现：

```bash
cwiki eval-all <dir> [--answer <answer-file>] [--wiki-only]
```

行为：

- 运行 wiki evaluation。
- 如果提供 `--answer`，评估指定 answer；否则自动选择 `.cwiki/answers/` 下最新的 `answer-*.md`。
- 只有提供 `--wiki-only` 或没有 answer 文件时，才跳过 answer evaluation。
- 同时展示分类分数；当两者都可用时展示综合分数。
- warning 保留到具体 wiki 文件或 answer 文件，方便追踪。

不调用模型。

### Phase 4：可选 JSON 输出

已实现：

参数：

```bash
--json
```

方便 CI 和 agent 自动化。

### Phase 5：LLM 辅助评估

只有在确定性评价稳定后，再加入可选的 LLM-assisted assessment 路径。

```bash
cwiki eval . --llm
cwiki eval-answer . answer.md --llm
cwiki eval-all . --answer answer.md --llm
```

agent 平台辅助评估：

```bash
cwiki eval-answer . answer.md --agent-eval-file .cwiki/eval/agent-assisted-eval.md --agent-model "current-agent-model"
cwiki eval-all . --answer answer.md --agent-eval-file .cwiki/eval/agent-assisted-eval.md --agent-model "current-agent-model"
```

行为：

- 始终先运行确定性 evaluation。
- 如果 `.env` 配置了模型，CLI 可以调用该模型生成 LLM-assisted 部分。
- 如果运行在 agent 平台中，agent 应使用当前会话模型生成 LLM-assisted 部分，而不是调用项目 `.env` 配置的模型，并用 `--agent-eval-file` 附加进报告。
- 如果没有 CLI 模型 key，保留确定性输出，并把 CLI LLM-assisted evaluation 标记为 `skipped`。
- LLM 参与的部分必须明确标注。
- 报告必须记录 provider、model、status 和 timestamp；agent 平台模式下 provider 可写为 `agent-platform`。
- 默认只把确定性报告、被引用页面、答案正文和必要 snippets 交给 LLM，不默认传入整个 wiki。
- LLM 输出应视为解释性建议，而不是事实真相来源。

### Phase 6：周期综合评估

已实现为本地 wiki 配置：

```bash
cwiki eval-schedule . --every-days 7 --llm
cwiki eval-schedule . --run-if-due
```

配置存储在 `.cwiki/eval/schedule.json`。它本身不会创建操作系统定时器；用户可以用 cron、Windows 任务计划、CI 或 agent 平台 automation 定期调用 `--run-if-due`。如果是 agent 平台 automation，优先运行确定性 CLI eval，然后用平台当前模型写入或总结 LLM-assisted 部分；只有希望 CLI 调用本地 `.env` 模型时才使用 `--llm`。

## 开放问题

- `wiki/synthesis.md` 是否必须有 Claim Ledger，还是可以通过链接页面间接引用？
- eval 低于某个阈值时是否应返回非零 exit code？
- answer evaluation 应支持纯文本答案，还是只支持 `.cwiki/answers/*.md`？
- `.cwiki/eval/index.md` 应保留全部历史报告，还是只保留最近 N 条？
- 快速变化领域的默认 stale threshold 应是多少？

## 推荐默认行为

- 默认打印人类可读报告。
- 默认把报告文件写入 `.cwiki/eval/`，并支持 `--no-write` 只输出到终端。
- 默认 exit `0`，除非存在 P1 问题或用户设置了 `--fail-under <score>`。
- 第一阶段不实现 LLM-assisted assessment，但报告结构要预留该能力，且不能替代确定性输出。
- 优先输出带文件路径的 warning，而不是抽象质量标签。
- 不把 evaluation 自动挂到普通命令后面；需要用户明确运行 `cwiki eval` 或 `cwiki eval-answer`。
- 支持 wiki 质量和问答质量分开评价；当用户明确要求整体质量时，支持生成综合评价报告。
- 当使用 LLM 辅助评估时，同时输出 deterministic 和 LLM-assisted 两个部分。
- `.cwiki/eval/` 默认保持 git ignored，除非用户明确改变该策略。
