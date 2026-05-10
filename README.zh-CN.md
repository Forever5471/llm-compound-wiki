# LLM Compound Wiki

LLM Compound Wiki 是一套“AI 持续维护的复利型知识库”开源脚手架。

它参考了 Andrej Karpathy 提出的 `llm-wiki` 概念原型，也吸收了现有社区项目的 workflow 经验，但我们这版的定位更偏通用基础设施：

- 不绑定 Claude，Codex、Claude Code、OpenCode、Cursor 或其他能读写文件的 agent 都能使用
- 默认兼容 Obsidian 的 Markdown 和 `[[wikilink]]`
- 提供零依赖 Python CLI，能初始化、索引、搜索、捕获来源、健康检查
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
├── bin/cwiki.py              零依赖 Python CLI
├── bin/cwiki.mjs             Node/npm 兼容包装器
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

### 1. 克隆项目

```bash
git clone https://github.com/Forever5471/llm-compound-wiki.git
cd llm-compound-wiki
```

### 2. 创建一个 wiki

```bash
python3 ./bin/cwiki.py init ./my-wiki --domain "AI 研究笔记"
cd my-wiki
python3 ../bin/cwiki.py lint .
```

这会创建 `raw/`、`wiki/`、`.cwiki/prompts/`、`CLAUDE.md`、`AGENTS.md`、`WIKI_SCHEMA.md` 和 workflow skills。

### 3. 添加资料

可以直接把资料放到 `my-wiki/raw/`，也可以用 `capture` 捕获 URL 或本地文件：

```bash
python3 ../bin/cwiki.py capture . https://example.com/article --title "示例文章"
python3 ../bin/cwiki.py capture . ./notes.md --title "项目笔记"
python3 ../bin/cwiki.py capture . ./产品方案.docx --title "产品方案"
python3 ../bin/cwiki.py capture . ./介绍材料.pptx --title "介绍材料"
python3 ../bin/cwiki.py capture . ./指标表.xlsx --title "指标表"
```

`capture` 会把原始资料记录到 `raw/captures/`，并在 `.cwiki/prompts/` 下生成 ingest prompt。当前内置支持 URL 记录、UTF-8 文本/Markdown、`.docx`、`.pptx`、`.xlsx` 的 OOXML 文本抽取，以及图片文件引用记录；`.pdf` 会优先调用本机 `pdftotext`，如果环境没有该命令，会明确提示先转换为 UTF-8 文本或走图片/OCR流程。

复杂格式走项目内置解析 skill：`wiki-parse-docx`、`wiki-parse-pdf`、`wiki-parse-image`、`wiki-parse-pptx`、`wiki-parse-xlsx`。本项目不会自动去外部 GitHub 寻找或集成解析项目；如果内置解析效果不够好，建议用户先自行使用其他工具把原文件转换成 Markdown 或 UTF-8 文本，再用本项目继续 capture、ingest、ask、answer。

摄入时默认保留原文件语言：中文资料会生成中文 wiki 页面，英文资料会生成英文 wiki 页面。只有在用户明确要求时才翻译。

### 4. 让智能体摄入

用 Codex、Claude Code、OpenCode、Cursor 或其他能读写文件的 agent 打开生成的 wiki 目录，然后说：

```text
Read CLAUDE.md and WIKI_SCHEMA.md, then process .cwiki/prompts/ingest-xxx.md.
```

智能体应该把资料编译进：

```text
wiki/
├── overview.md
├── synthesis.md
├── summaries/
├── entities/
├── concepts/
├── comparisons/
├── index.md
└── log.md
```

### 5. 维护和搜索

```bash
python3 ../bin/cwiki.py index .
python3 ../bin/cwiki.py lint .
python3 ../bin/cwiki.py search . "retrieval"
python3 ../bin/cwiki.py ask . "这个 wiki 对 retrieval 有什么结论？"
python3 ../bin/cwiki.py web-ask . "这个主题最近有什么变化？" --wiki-weight 0.6 --web-weight 0.4
OPENAI_API_KEY=... python3 ../bin/cwiki.py answer . "这个 wiki 对 retrieval 有什么结论？"
```

## 可选 npm 包装器

如果仍然想要 npm 风格的全局 `cwiki` 命令，也可以安装；npm 入口只是转发到 Python：

```bash
npm install -g .
cwiki init ./my-wiki --domain "竞品研究"
cwiki search ./my-wiki "pricing"
cwiki lint ./my-wiki
```

仓库仍保留 `bin/cwiki.mjs` 作为 npm/Node 兼容包装器，但实际实现已经迁到 `bin/cwiki.py`。

依赖要求：

- Python 3.10+
- 只有在需要全局 `cwiki` 包装命令时才需要 Node/npm

## 命令

```bash
cwiki init <dir> [--domain "..."]
cwiki index <dir>
cwiki lint <dir>
cwiki search <dir> <query>
cwiki ask <dir> <question> [--top-k 6] [--show-context]
cwiki web-ask <dir> <question> [--top-k 6] [--max-web-sources 6] [--wiki-weight 0.6] [--web-weight 0.4] [--no-web] [--show-context]
cwiki answer <dir> <question> [--provider openai|glm] [--model "..."] [--top-k 6]
cwiki capture <dir> <file-or-url> [--title "..."]
```

`capture` 不会假装自己已经理解了来源。它会把文件或 URL 捕获到 `raw/captures/`，并在 `.cwiki/prompts/` 里生成一份 ingest prompt。随后由 agent 按 `WIKI_SCHEMA.md` 和 `.agents/skills/` 的流程把来源编译进 `wiki/` 的合适分区。

`ask` 也不会直接调用大模型。它会用混合检索搜索已经编译好的 wiki：关键词检索负责精确命中，轻量向量检索负责缓解同义词和长文本漏召回，关系检索会沿 `[[wikilink]]` 把相邻页面补进上下文。随后它在 `.cwiki/prompts/` 下生成给模型看的 query prompt，同时在 `.cwiki/briefs/` 下生成给人快速阅读的 evidence brief。brief 适合先粗看，prompt 适合交给 Codex、Claude Code 或其他 agent 生成完整答案。

`web-ask` 用于“本地 wiki + 实时网络资料”的问题。它会先做本地混合检索，再生成三类中间产物：`.cwiki/prompts/web-query-*.md` 负责浏览器研究任务，`.cwiki/web-research/web-research-*.md` 负责沉淀联网搜索结果，`.cwiki/prompts/fusion-*.md` 负责把本地 wiki 证据和 web 证据交给后续 agent 做综合性回答。默认权重是本地 wiki `0.6`、web search `0.4`；可以用 `--wiki-weight` 和 `--web-weight` 调整。`--web-weight 0` 或 `--no-web` 会关闭联网搜索，只生成本地 wiki-only 的融合 prompt。

具备浏览器/搜索能力的 agent 使用 `wiki-agent-browser` 时，应先读本地 wiki，再联网搜索，打开正文后再引用，并把搜索结果写入 `.cwiki/web-research/`。最终回答中要区分本地证据、网络证据、综合结论和缺口。每条外部事实都必须带 URL 和访问日期；值得长期保留的网页需要先 `cwiki capture . <url> --title "<title>"`，再摄入到 `wiki/`。

`answer` 会真正调用模型，并把草稿答案写到 `.cwiki/answers/`。目前支持 OpenAI Responses API 和 GLM OpenAI-compatible Chat Completions。它会先生成同样的 query prompt 和 human brief，因此答案可追溯。草稿答案不会自动写入 `wiki/`，建议人工确认后再让 agent 把有价值的综合沉淀进编译层。

## 模型配置

可以在项目目录或具体 wiki 目录下创建本地 `.env`。`.env` 默认不进 git，适合放 API key：

```bash
CWIKI_PROVIDER=glm
CWIKI_GLM_MODEL=glm-4.6v
GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GLM_API_KEY=your-local-key

# web-ask 默认策略
CWIKI_WEB_WIKI_WEIGHT=0.6
CWIKI_WEB_WEIGHT=0.4
CWIKI_WEB_MAX_SOURCES=6
CWIKI_WEB_ENABLED=true
```

然后直接运行：

```bash
python3 ../bin/cwiki.py answer . "gray_zone是怎么设计的"
```

也可以在命令行临时覆盖：

```bash
python3 ../bin/cwiki.py answer . "gray_zone是怎么设计的" --provider glm --model glm-4.6v
```

`web-ask` 会读取这些 `.env` 默认值；命令行参数优先级更高。例如下面会临时覆盖 `.env`：

```bash
python3 ../bin/cwiki.py web-ask . "问题" --wiki-weight 0.8 --web-weight 0.2
python3 ../bin/cwiki.py web-ask . "问题" --no-web
```

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

同时会生成 `wiki-init`、`wiki-capture`、`wiki-parse-docx`、`wiki-parse-pdf`、`wiki-parse-image`、`wiki-parse-pptx`、`wiki-parse-xlsx`、`wiki-ingest`、`wiki-query`、`wiki-agent-browser`、`wiki-update`、`wiki-lint` 等技能：`.claude/skills/` 里放 canonical 定义，`.agents/skills/` 里放兼容入口。

## 开源定位

这不是另一个封闭知识库产品，而是一套可 fork、可改、可放进 Obsidian、可被任意 agent 操作的文件系统协议。

MIT License
