# 问答工作流

本文档说明初始化后的 LLM Compound Wiki 推荐如何回答问题。

## 模式

### CLI 准备 prompt

`cwiki ask <dir> "<question>"` 默认不会调用大模型。它会检索本地 wiki，并写出：

- `.cwiki/prompts/query-*.md`：给回答 agent 或 LLM 使用。
- `.cwiki/briefs/brief-*.md`：给人快速检查证据。

当你希望先获得一个可复现的证据边界，再让 agent 生成最终文字时，用这条路径。

可以用 `--retrieval auto|direct|graph|path|synthesis` 控制 graph-aware 上下文加入的深度。`auto` 会根据问题复杂度选择计划，在计划内部只执行必要阶段，并在 prompt 的 Retrieval Trace 中记录预算、跳过阶段和早停原因。

如果希望在写出 prompt 前让模型参与图候选排序，可以加 `--graph-rerank`。这会调用 `.env` 或命令行配置的大模型，对 graph/path/synthesis 的 final context candidates 做语义重排，并把重排状态、理由和 gaps 写入 Retrieval Trace。

### 分层检索策略

- `direct`：只使用直接关键词/向量命中的页面。适合单点事实查询。
- `graph`：在 direct hits 基础上加入 wikilink 或 typed relationship 的入边/出边邻居页面。适合需要附近概念、角色、模块或相关实体的查询。
- `path`：在 graph 上下文基础上加入 top hits 之间的最短路径证据。适合流程、机制、依赖、关系、how/why 类问题。
- `synthesis`：加入 direct、graph、path 证据，以及 `overview.md`、`synthesis.md` 和中心节点。适合综合总结、对比、取舍、策略和评估类问题。
- `auto`：由 CLI 根据问题自动选择。若 `auto` 选中 `path` 但没有找到任何路径证据，会自动回退到 `graph`，并在 Retrieval Trace 中写明回退原因。

图检索不是把图谱当作事实来源，而是把 `.cwiki/graph/graph.json` 当作由 wikilink 和有来源支撑的 `## Relationships` 行生成的导航层：direct hits 是主证据，Graph-Expanded Pages 是邻近上下文，Path Evidence 用来解释页面之间的关系，Final Context Pages 是本次可复现的证据包。

### CLI 调模型回答

`cwiki answer <dir> "<question>"` 会调用 `.env` 配置的 provider/model，并把草稿写入 `.cwiki/answers/`。

这条路径偏终端使用。它会使用本地 wiki 检索和配置的大模型，但不会执行实时联网搜索。

它和 `ask` 使用同一套 retrieval strategy，因此后续 answer evaluation 可以读取关联 query prompt，并评价本次检索质量。

加 `--graph-rerank` 时，`answer` 会先进行 LLM 图重排，再把重排后的 Context Pack 交给最终回答模型；因此一次命令会发生“图重排模型调用 + 最终回答模型调用”两次模型调用。

### Agent 平台混合式回答

在 Codex、Trae、Claude Code、Cursor、OpenCode 或其他能读写文件系统的 agent 中，推荐使用这条路径。

1. 如果还没有合适的 query prompt，先运行 `cwiki ask . "<question>"`。
2. 读取生成的 query prompt 和 evidence brief。
3. 从磁盘读取 prompt 中列出的所有 wiki 页面，以及 `wiki/index.md`。
4. 把这个 prompt 视为可复现的证据边界。
5. 如果 context pack 不完整，再额外检查高价值 wiki 页面，并沿有用的 `[[wikilink]]` 追一层。
6. 如果问题需要实时网络证据，运行 `cwiki web-ask . "<question>"` 并遵循 `wiki-agent-browser`。
7. 最终文字由当前 agent 平台模型生成，而不是项目 `.env` 中配置的模型；除非用户明确要求运行 `cwiki answer`。

当已有草稿答案后，如果 `## Gaps` 写明缺少案例、量化指标、最新事实或实施指南，运行 `cwiki eval-answer . <answer-file> --web-on-gaps`。它会生成 `.cwiki/web-gaps/`、web research、web capture checklist 和 fusion prompt 产物，让下一轮真的去补外部证据，而不是只在报告里停留于“缺少证据”。

## 回答结构

混合式回答应使用：

```markdown
## Evidence Used

- [[page-a]] - used - source: raw/example.md
- [[page-b]] - not used - reason: 相关但本问题不需要
- [[extra-page]] - used - source: raw/other.md

## Answer

直接回答。正文中使用 `[[page-a]]` 引用，并在事实附近保留 source path 或 URL。

## Gaps

已知缺口、弱覆盖、限制、未使用的相关页，或写明“基于已检查的 wiki 上下文，暂无已知缺口”。
```

## 为什么需要混合式

生成的 prompt 让回答可审计、可复现。agent 的额外检查可以避免一次召回不足把答案限制死。最终答案仍必须受 wiki 页面、source path、URL 和显式 gaps 约束。
