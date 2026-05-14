# 问答工作流

本文档说明初始化后的 LLM Compound Wiki 推荐如何回答问题。

## 模式

### CLI 准备 prompt

`cwiki ask <dir> "<question>"` 不会调用大模型。它会检索本地 wiki，并写出：

- `.cwiki/prompts/query-*.md`：给回答 agent 或 LLM 使用。
- `.cwiki/briefs/brief-*.md`：给人快速检查证据。

当你希望先获得一个可复现的证据边界，再让 agent 生成最终文字时，用这条路径。

### CLI 调模型回答

`cwiki answer <dir> "<question>"` 会调用 `.env` 配置的 provider/model，并把草稿写入 `.cwiki/answers/`。

这条路径偏终端使用。它会使用本地 wiki 检索和配置的大模型，但不会执行实时联网搜索。

### Agent 平台混合式回答

在 Codex、Trae、Claude Code、Cursor、OpenCode 或其他能读写文件系统的 agent 中，推荐使用这条路径。

1. 如果还没有合适的 query prompt，先运行 `cwiki ask . "<question>"`。
2. 读取生成的 query prompt 和 evidence brief。
3. 从磁盘读取 prompt 中列出的所有 wiki 页面，以及 `wiki/index.md`。
4. 把这个 prompt 视为可复现的证据边界。
5. 如果 context pack 不完整，再额外检查高价值 wiki 页面，并沿有用的 `[[wikilink]]` 追一层。
6. 如果问题需要实时网络证据，运行 `cwiki web-ask . "<question>"` 并遵循 `wiki-agent-browser`。
7. 最终文字由当前 agent 平台模型生成，而不是项目 `.env` 中配置的模型；除非用户明确要求运行 `cwiki answer`。

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
