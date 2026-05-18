# LLM Compound Wiki — Agent 中文说明

领域：{{domain}}

今天日期：{{date}}

> 重要：这是一个由 LLM 维护的 wiki。人类拥有 `raw/`，LLM 维护 `wiki/`。

## 这是什么

这是一个 compounding wiki，灵感来自 Karpathy 的 LLM Wiki 模式。

`wiki/` 是由 LLM 生成和维护的 Markdown 知识层，包括：

- summaries
- entity pages
- concept pages
- comparisons
- overview map
- synthesis thesis

LLM 负责创建页面、在新来源到来时更新页面、维护交叉引用并保持 wiki 一致。用户阅读它，LLM 编译和维护它。

## 必读文件

任何 wiki 操作前，先读：

1. `WIKI_SCHEMA.md`
2. `wiki/index.md`
3. `wiki/` 下相关页面

规范 skills 位于 `.claude/skills/`。当任务匹配时优先使用。

## 执行模型

- CLI 是脚手架和本地工具层：初始化、capture、index、lint、search、生成 prompt/brief、评估。
- `graph` 和 `graph-report` 从已编译 wiki 页面与 `[[wikilink]]` 创建确定性图谱层。
- agent 智能运行在当前平台。除非用户明确要求运行 CLI 命令，否则推理和最终文字使用当前 agent 模型。
- 本地 skills 是 agent 指令，不是可执行 CLI 插件。
- `ask` 和 `web-ask` 准备证据和 prompt；它们不调用 LLM。
- `answer` 调用 `.env` 配置的 provider/model，并基于本地 wiki 检索；它不执行实时联网搜索。
- 实时联网研究需要浏览器能力 agent 按 `wiki-agent-browser` 执行。

## Agent 平台混合问答流程

在 Codex、Trae、Claude Code、Cursor、OpenCode 等 agent 平台中回答 wiki 问题时使用。

1. 如果没有合适的 query prompt，运行 `cwiki ask . "<question>" --retrieval auto`。
2. 读取生成的 `.cwiki/prompts/query-*.md` 和 `.cwiki/briefs/brief-*.md`；把 prompt 当作可复现证据边界。
3. 从磁盘完整读取 prompt 列出的所有相关页面，并读取 `wiki/index.md`。
4. 如果 prompt 上下文不完整，再搜索 wiki、检查高信号页面，并沿有用的 `[[wikilink]]` 追一层。
5. 如果问题需要当前网络证据，运行 `cwiki web-ask . "<question>"` 并使用 `wiki-agent-browser`；不要凭记忆编造当前事实。
6. 最终文字来自当前 agent 模型，而不是 `.env`，除非用户明确要求运行 `cwiki answer`。
7. 回答使用 `## Evidence Used`、`## Answer`、`## Gaps`。
8. `## Evidence Used` 中要把 prompt 列出的页面标为 `used` 或 `not used - reason`，并列出额外检查的 wiki 页面或 web 来源。

## 分层检索策略

- `direct`：直接关键词/向量命中。用于窄事实查询。
- `graph`：direct hits 加入 `.cwiki/graph/graph.json` 的入边/出边邻居。用于附近概念、角色、模块、实体可能重要的问题。
- `path`：direct hits、图谱邻居和 top hits 之间的最短路径证据。用于流程、机制、依赖、关系、how/why 问题。
- `synthesis`：direct、graph、path，加上 `overview.md`、`synthesis.md` 和中心节点。用于综合总结、对比、取舍、策略和评估。
- `auto`：CLI 自动选择层级。如果 `auto` 选择 `path` 但没有路径证据，会回退到 `graph`，并记录在 Retrieval Trace。

图检索不是事实来源，而是导航层。读 Retrieval Trace 时：

- Direct Hits 是主证据。
- Graph-Expanded Pages 是邻近上下文。
- Path Evidence 解释页面关系。
- Final Context Pages 是可复现证据包。

当语义重排值得额外调用一次模型时，可以运行 `cwiki ask . "<question>" --graph-rerank` 或 `cwiki answer . "<question>" --graph-rerank`。回答前读取 `LLM Graph Rerank` 区块，但事实依据仍以页面正文、Claim Ledger 和 source path 为准。

## 本地配置

- `.env.example` 是本地模型与 web-search 默认配置模板。
- 运行 `cwiki answer` 前，将 `.env.example` 复制为 `.env` 并填入 provider/API key。
- `.env` 被 git 忽略，不应提交。
- `.env` 影响终端/CLI 流程，例如 `cwiki answer`；不会改变当前 agent 平台的聊天模型。
- `cwiki answer` 使用配置的 provider/model 与本地 wiki 检索，但不执行实时联网搜索。
- `web-ask` 读取 `.env` 中的 `CWIKI_WEB_WIKI_WEIGHT`、`CWIKI_WEB_WEIGHT`、`CWIKI_WEB_MAX_SOURCES`、`CWIKI_WEB_ENABLED` 等默认值；命令行参数优先。
- `answer --web-on-gaps` 和 `eval-answer --web-on-gaps` 会识别需要外部证据的缺口，并生成 `.cwiki/web-gaps/`、`web-query-*`、`web-research-*`、`fusion-*` 产物。默认读取同一组 `CWIKI_WEB_*`，除非用 `--web-gap-*` 单次覆盖。
- CLI 会把 `answer`、图重排和 `--llm` evaluation 的模型用量自动记录到 `.cwiki/usage/llm-usage.jsonl`。
- 如果当前 agent 平台能显示 ingest、update、浏览器研究、最终回答或其它平台模型工作的 token/费用，用 `cwiki usage-log . --operation <step> --provider agent-platform --model <visible-model-name> ...` 手动补记。
- 需要完整成本报告时运行 `cwiki usage-report .`；可用 `--operation`、`--artifact`、`--question`、`--provider`、`--model`、`--since`、`--until` 过滤。
- agent 平台内的 LLM-assisted evaluation 应使用当前 agent 模型。将辅助评估写入 `.cwiki/eval/agent-assisted-*.md`，再用 `--agent-eval-file <file> --agent-model <visible-model-name>` 附加进正式报告，报告会记录 `provider: agent-platform`。

## 目录契约

```text
raw/              人类拥有的不可变源材料
wiki/             LLM 维护的编译知识层
  overview.md     持久地图和早期入口
  synthesis.md    成熟知识的跨页面综合论点
  summaries/      来源和主题摘要
  entities/       人、组织、地点、产品、项目
  concepts/       概念、理论、方法、术语
  comparisons/    对比页和决策矩阵
  index.md        内容目录
  log.md          追加式操作日志
.cwiki/prompts/   生成的工作 prompt，不是知识
.cwiki/graph/     生成的图谱产物，不是规范知识
```

## 不可妥协规则

- 除非用户明确要求，不要编辑 `raw/`。
- 不要把生成知识放到 `wiki/` 之外。
- 不要把 `.cwiki/prompts/` 当作知识。
- 不要把 `.cwiki/graph/` 当作事实来源；它过期时从 `wiki/` 重新生成。
- 每个事实性 claim 都需要 source path 或 URL。
- 保持源语言。中文来源生成中文页面，英文来源生成英文页面；除非用户要求，不要默认翻译。
- 优先更新已有页面，避免创建孤立页面。
- 使用 Obsidian wikilinks，例如 `[[retrieval-augmented-generation]]`。
- 保留矛盾和不确定性。
- 每次 ingest 或保存分析后更新 `wiki/index.md`。
- 追加 `wiki/log.md`，不要重写历史。
- `wiki/overview.md` 和 `wiki/synthesis.md` 是两个可选第一阅读面，不是占位页。
- 每次 ingest 或 update 后刷新 `overview.md` 和 `synthesis.md`；一旦有真实知识，不要保留通用种子文本。

## 自动触发工作流

### Ingest

当用户说 ingest、process、add to wiki、summarize this source、read this URL/file，或指向 raw source 时触发。

如果来源尚未 capture，先使用 `wiki-capture`。复杂格式先走解析 skill：`wiki-parse-docx`、`wiki-parse-pdf`、`wiki-parse-image`、`wiki-parse-pptx`、`wiki-parse-xlsx`。

步骤：

1. 完整读取来源。
2. 读取 `wiki/index.md` 和相关已有页面。
3. 除非用户要求翻译，否则保持源语言。
4. 识别受影响的 summaries、entities、concepts、comparisons、overview、synthesis。
5. 在正确的 `wiki/` 分区创建或更新页面。
6. 刷新 `wiki/overview.md`，写入当前地图、入口链接和开放导航问题。
7. 刷新 `wiki/synthesis.md`，写入稳定 claims、矛盾、证据清单，或说明为什么尚未形成 thesis。
8. 增加有来源支撑的 Claim Ledger 行。
9. 需要时添加双向 wikilinks。
10. 运行 `cwiki index .`。
11. 追加 `wiki/log.md`。

### Query

当用户询问 wiki 知识时触发。

步骤：

1. 优先运行 `cwiki ask . "<question>" --retrieval auto`，除非已有合适 query prompt。
2. 读取生成的 query prompt 和 evidence brief。
3. 读取 Retrieval Trace，理解 direct hits、graph-expanded pages、path evidence。
4. 读取 `wiki/index.md` 和相关页面全文。
5. 如果 prompt 上下文不足，沿相关 wikilinks 追一层。
6. 使用 `[[topic]]` 和 source path / URL 回答。
7. 明确写出 gaps，包括额外检查页面、未使用的 prompt 页面和证据限制。
8. 重要综合结论应建议保存到 `wiki/synthesis.md`、`wiki/comparisons/` 或其它合适页面。

### Graph

当用户询问关系、路径、影响分析、中心概念、孤立页面或图结构时触发。

步骤：

1. 运行 `cwiki graph-report .`。
2. 读取 `.cwiki/graph/graph.md`。
3. 用 `cwiki path . <from> <to>` 查询显式关系路径。
4. 用 `cwiki explain . <slug>` 查看节点级入链、出链、来源和度数。
5. 引用本地页面为 `[[slug]]`，并说明图谱只反映已有 wikilinks。

### Agent Browser

当问题需要当前、最新、市场、政策、价格、benchmark、release、新闻或实时网络证据时触发。

步骤：

1. 运行 `cwiki web-ask . "<question>"`。
2. 读取生成的 browser prompt 和 fusion prompt。
3. 先读本地 wiki 上下文，再浏览。
4. 搜索并打开来源页面；不要引用搜索结果摘要。
5. 将 web findings 写入 `.cwiki/web-research/*.md`。
6. 最终答案分开写 local wiki evidence、web evidence、synthesis、gaps、sources。
7. 重要 web 来源先 `cwiki capture`，再摄入 `wiki/`。

如果已有答案或评估的 gaps 指出缺少案例、量化指标、最新事实或迁移/实施指南，先运行 `cwiki eval-answer . <answer-file> --web-on-gaps`。随后使用生成的 web gap report 和 fusion prompt 交接浏览器研究。

### Evaluation

当用户明确要求评估 wiki 质量、回答质量或综合质量时触发。

步骤：

1. 运行确定性评估：`cwiki eval .`、`cwiki eval-answer . <answer>` 或 `cwiki eval-all . --answer <answer>`。
2. 如果在 CLI 中使用 `.env` 模型辅助评估，使用 `--llm`。
3. 如果在 agent 平台中辅助评估，当前 agent 先写 `.cwiki/eval/agent-assisted-*.md`，再运行：

```bash
cwiki eval-answer . <answer> --agent-eval-file .cwiki/eval/agent-assisted-*.md --agent-model "<visible-model-name>"
```

4. LLM-assisted evaluation 只能补充风险、优先级和定性判断，不能覆盖确定性 warning 或分数。
