# 设计优化 Spec：默认零依赖、可扩展检索、可恢复流程

状态：已采纳
日期：2026-05-19

## 背景

当前项目已经具备 `init`、`capture`、`ask`、`answer`、轻量图检索、LLM 图重排、web gap follow-up、LLM 成本记录等能力。但随着项目从“概念原型”走向“开源工具”，有几处设计表述和工程边界需要收紧，避免误导用户，也降低后续维护成本。

本次优化遵循一个原则：默认路径保持简单、可本地运行、零外部依赖；中大规模、复杂语义或高价值场景允许接入更重的能力。

## 目标

1. 把“不需要 embedding 服务”调整为“默认不需要；中大规模可选 embedding/vector index”。
2. 避免继续扩大 `bin/cwiki.py` 的职责，新增能力优先进入模块。
3. 明确当前 graph 是 `link graph`，不是 typed knowledge graph 或 semantic graph。
4. web research 结果必须有可沉淀为 raw source 的清单，避免长期追溯断链。
5. 为 ingest 增加确定性、可恢复的状态机：`status -> ingest-plan -> apply -> validate -> index -> link-graph -> eval`。

## 非目标

- 本次不实现真正的 embedding API、向量数据库或 ANN 索引。
- 本次不实现实体-关系抽取式 typed graph。
- 本次不让 CLI 直接联网浏览网页。联网仍由具备 browser/search 能力的 agent 执行。
- 本次不自动把 web research 写入 `wiki/`，仍需 capture、ingest 和用户可审查的步骤。

## 设计决策

### 1. Embedding 定位

旧定位“无需 embedding 服务”容易被理解为项目永远排斥 embedding。新定位为：

- 默认零依赖：小规模个人 wiki 使用关键词、本地 hash-vector 和 link graph 即可。
- 可选增强：当页面数、文档长度、同义词、跨语言或语义漂移问题变大时，可以接入 embedding/vector index 作为粗筛层。
- 关系检索仍然保留：向量召回只解决语义相似，不替代 link graph、path evidence、claim ledger 和 synthesis 页面。

验收标准：

- README 和模板文档不再宣称绝对“不需要 embedding 服务”。
- 文档明确当前 hash-vector 不是 embedding API。
- 文档保留未来可选 embedding/vector index 的扩展口。

### 2. Thin Harness, Fat Skills / Modules

`bin/cwiki.py` 已经承担 CLI、解析、检索、图、LLM、web prompt、成本统计等职责。短期内不做一次性大拆分，避免引入大范围回归；但新增能力必须优先落在模块中。

本次先新增 `cwiki_core.ingest_workflow`：

- 负责 ingest run 的创建、状态更新、状态渲染。
- CLI 只做参数解析和输出。
- 后续可以继续把 web workflow、usage、link graph、retrieval 拆到同一包下。

验收标准：

- 新增 ingest 状态机逻辑不写进 `bin/cwiki.py` 主体深处。
- CLI 只暴露薄封装命令。
- 测试覆盖创建、查看和更新 run。

### 3. Graph 命名

当前 graph 是从页面、frontmatter、Claim Ledger 和 `[[wikilink]]` 派生的导航图。它不包含 typed entity-relation schema，也不做 LLM 实体抽取。

命名约定：

- `link graph`：当前已实现，文件仍保存在 `.cwiki/graph/`，命令 `graph`/`graph-report` 保留兼容。
- `typed graph`：未来可选，实体、关系、类型、置信度、来源 span。
- `semantic graph`：未来可选，可能结合 embedding、LLM 抽取、社区发现或语义聚类。

验收标准：

- README、AGENTS、WIKI_SCHEMA 说明当前是 link graph / wikilink navigation graph。
- 新增 `link-graph` 和 `link-graph-report` 别名，原有 `graph` 命令保留。
- 用户不应误以为当前已经具备完整知识图谱能力。

### 4. Web Research 沉淀

`.cwiki/web-research/` 是工作产物，不应成为长期唯一来源。只要生成 web research 流程，就同步生成 `.cwiki/web-captures/web-captures-*.md`，作为“哪些网页应该 capture 到 raw/captures/”的检查清单。

要求：

- browser agent 填写 web research 时，也要维护 capture checklist。
- 对最终答案产生实质影响的 web source，必须在 checklist 中明确是否需要 capture。
- 值得沉淀的网页先运行 `cwiki capture . <url> --title "<title>"`，再走 ingest。

验收标准：

- `web-ask` 和 `--web-on-gaps` 都生成 web capture checklist。
- web query、research、fusion、brief、gap report 都引用该 checklist。
- `.gitignore` 忽略 `.cwiki/web-captures/**`。

### 5. Ingest 状态机

原版 LLM Wiki 可以让 agent 自由完成 wiki 编译，但开源项目需要更方便、更可恢复。新增 ingest run 状态机：

1. `status`：确认 wiki 当前状态、原始来源和最新 ingest prompt。
2. `ingest-plan`：生成本次 ingest run 的 JSON 和 Markdown 计划。
3. `apply`：agent 按 prompt 更新 `wiki/` 页面。
4. `validate`：检查 schema、source citation、overview/synthesis 是否更新。
5. `index`：运行 `cwiki index .`。
6. `link-graph`：运行 `cwiki link-graph-report .` 或兼容命令 `graph-report`。
7. `eval`：运行 `cwiki eval .` 或相关质量评估。

新增命令：

- `cwiki status <dir>`：查看最新 ingest run 或显示待创建状态。
- `cwiki ingest-plan <dir> [--source ...] [--prompt ...] [--run-id ...]`：创建可恢复 ingest run。
- `cwiki ingest-status <dir> [run]`：查看指定或最新 run。
- `cwiki ingest-step <dir> [run] <step> --status pending|in_progress|completed|blocked [--note ...]`：更新步骤状态。

验收标准：

- 状态保存在 `.cwiki/ingest-runs/` 的 JSON 和 Markdown 中。
- 可从中断步骤恢复，不依赖终端历史。
- `.gitignore` 忽略 `.cwiki/ingest-runs/**`。

## 后续路线

- Phase 2：把 web workflow 和 usage report 也迁入 `cwiki_core`。
- Phase 3：实现可选 embedding/vector coarse retrieval，默认关闭。
- Phase 4：实现 typed graph 实验命令，明确区别于当前 link graph。
- Phase 5：让 ingest run 自动串联 deterministic checks，并输出更完整的 run report。
