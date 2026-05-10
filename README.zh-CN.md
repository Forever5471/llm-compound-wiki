# LLM Compound Wiki

LLM Compound Wiki 是一套“AI 持续维护的复利型知识库”开源脚手架。

它参考了 Andrej Karpathy 提出的 `llm-wiki` 概念原型，也吸收了现有社区项目的 workflow 经验，但我们这版的定位更偏通用基础设施：

- 不绑定 Claude，Codex、Claude Code、OpenCode、Cursor 或其他能读写文件的 agent 都能使用
- 默认兼容 Obsidian 的 Markdown 和 `[[wikilink]]`
- 提供零依赖 CLI，能初始化、索引、搜索、捕获来源、健康检查
- 明确区分 `raw/` 原始证据和 LLM 完全拥有的 `wiki/` 编译知识层

## 为什么要做

传统 RAG 往往是在每次提问时重新检索、重新拼接、重新生成。LLM Compound Wiki 的思路是：让 AI 把知识“编译”成一个持续演化的 wiki。

每加入一个来源，agent 不只是保存它，而是：

- 提取可追踪的事实声明
- 更新相关主题页
- 添加双向链接
- 标注矛盾和不确定性
- 更新 `wiki/index.md`
- 追加 `wiki/log.md`

这样知识会累积，而不是散落在一次次对话里。

## 目录结构

```text
.
├── AGENTS.md                 本项目开发规则
├── bin/cwiki.mjs             零依赖 CLI
├── templates/                初始化 wiki 时复制的模板
│   ├── AGENTS.md
│   ├── CLAUDE.md
│   ├── WIKI_SCHEMA.md
│   ├── .claude/skills/       canonical skill 定义
│   └── .agents/skills/       兼容其他 agent 的入口
├── raw/                      用户私有原始材料，默认不进 git
├── .cwiki/prompts/           生成的 ingest 工作提示，默认不进 git
├── wiki/
│   ├── overview.md           整个知识库的全局地图
│   ├── synthesis.md          跨来源综合结论
│   ├── summaries/            来源摘要和主题摘要
│   ├── entities/             人物、组织、产品、项目等实体
│   ├── concepts/             概念、方法、理论、术语
│   ├── comparisons/          对比、取舍和决策矩阵
│   ├── index.md              全库索引
│   └── log.md                追加式操作日志
```

## 快速开始

```bash
node ./bin/cwiki.mjs init ./my-wiki --domain "AI 研究笔记"
cd my-wiki
node ../bin/cwiki.mjs capture . https://example.com/article --title "示例文章"
node ../bin/cwiki.mjs lint .
```

如果作为 npm 包安装：

```bash
npm install -g .
cwiki init ./my-wiki --domain "竞品研究"
cwiki search ./my-wiki "pricing"
cwiki lint ./my-wiki
```

## 命令

```bash
cwiki init <dir> [--domain "..."]
cwiki index <dir>
cwiki lint <dir>
cwiki search <dir> <query>
cwiki capture <dir> <file-or-url> [--title "..."]
```

`capture` 不会假装自己已经理解了来源。它会把文件或 URL 捕获到 `raw/captures/`，并在 `.cwiki/prompts/` 里生成一份 ingest prompt。随后由 agent 按 `WIKI_SCHEMA.md` 和 `.agents/skills/` 的流程把来源编译进 `wiki/` 的合适分区。

## 页面规范

```markdown
---
title: Topic Name
kind: concept
tags: [tag-a, tag-b]
sources: 2
updated: 2026-05-08
status: active
---

# Topic Name

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| ... | raw/example.md | medium | 2026-05-08 |

## Synthesis

## Related

- [[another-topic]] - 关系说明

## Open Questions
```

这里的 `Claim Ledger` 是我们这版相对轻量模板的关键补强：每个事实声明都能追溯到来源，后续更新时不用整页重写。

## Agent 工作流

1. 改 wiki 前先读 `WIKI_SCHEMA.md`。
2. `raw/` 只读，作为证据层保存。
3. 按类型写入 `wiki/summaries/`、`wiki/entities/`、`wiki/concepts/`、`wiki/comparisons/`，并维护 `overview.md` 和 `synthesis.md`。
4. 事实声明必须有来源路径或 URL。
5. ingest 或保存分析后运行 `cwiki index .`。
6. 每隔几次 ingest 运行 `cwiki lint .`，处理断链、孤页和过期声明。

初始化后的 wiki 会同时生成 `CLAUDE.md`、`AGENTS.md` 和 `WIKI_SCHEMA.md`。`CLAUDE.md` 是给 Claude Code 这类智能体看的强入口文件，`AGENTS.md` 是更通用的 agent 入口，`WIKI_SCHEMA.md` 是详细的 wiki 结构协议。

同时会生成 `wiki-init`、`wiki-ingest`、`wiki-query`、`wiki-update`、`wiki-lint` 五个技能：`.claude/skills/` 里放 canonical 定义，`.agents/skills/` 里放兼容入口。

## 开源定位

这不是另一个封闭知识库产品，而是一套可 fork、可改、可放进 Obsidian、可被任意 agent 操作的文件系统协议。

MIT License
