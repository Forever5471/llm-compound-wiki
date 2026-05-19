# AGENTS.zh-CN.md

这是一个 LLM Compound Wiki。

## 分层规则

- `raw/` 是人类拥有的不可变源材料。除非用户明确要求，不要编辑或删除。
- `wiki/` 是 AI 维护的编译知识层：summaries、entities、concepts、comparisons、overview 和 synthesis。
- `.cwiki/prompts/` 是生成的工作 prompt，不是知识库正文。
- `.cwiki/graph/` 是从 `wiki/` 和 `[[wikilink]]` 生成的 link graph 导航层，不是事实来源本身，也不是 typed knowledge graph。
- `wiki/index.md` 是内容目录。每次摄入或保存分析后都要更新。
- `wiki/log.md` 是追加日志。不要重写历史。

## 必读文件

在修改 wiki 内容前，先读：

1. `WIKI_SCHEMA.md`
2. `CLAUDE.zh-CN.md` 或 `CLAUDE.md`
3. `wiki/index.md`
4. 相关 wiki 页面

## 执行模型

- CLI 是脚手架和本地工具层：初始化、capture、index、lint、search、生成 prompt/brief、评估。
- `link-graph` 和 `link-graph-report` 从已编译 wiki 页面与 `[[wikilink]]` 生成确定性 link graph；`graph` 和 `graph-report` 是兼容别名。
- agent 智能运行在当前平台。除非用户明确要求运行 CLI 模型命令，否则最终推理和文字由当前 agent 模型完成。
- 本地 skills 是给 agent 看的说明，不是可执行 CLI 插件。
- `ask` 和 `web-ask` 只准备证据和 prompt，不调用大模型。
- `answer` 会调用 `.env` 配置的 provider/model，并只基于本地 wiki 检索，不执行实时联网搜索。
- 实时联网研究需要具备浏览器能力的 agent 按 `wiki-agent-browser` 执行。

## Agent 平台混合问答流程

在 Codex、Trae、Claude Code、Cursor、OpenCode 等 agent 平台里回答 wiki 问题时使用。

1. 如果没有合适的 query prompt，先运行 `cwiki ask . "<question>" --retrieval auto`。
2. 阅读 `.cwiki/prompts/query-*.md` 和 `.cwiki/briefs/brief-*.md`；把 prompt 当作可复现证据边界。
3. 从磁盘完整读取 prompt 中列出的相关页面，并读取 `wiki/index.md`。
4. 如果 prompt 上下文不足，再搜索 wiki、检查高价值相邻页面，并沿有用的 `[[wikilink]]` 追一层。
5. 如果问题需要实时网络证据，运行 `cwiki web-ask . "<question>"` 并使用 `wiki-agent-browser`；不要凭模型记忆编造当前事实。
6. 最终文字来自当前 agent 模型，而不是 `.env`，除非用户明确要求运行 `cwiki answer`。
7. 回答必须包含 `## Evidence Used`、`## Answer`、`## Gaps`。
8. 在正文中用 `[[slug]]` 引用 wiki 页面，并在事实性 claim 附近保留 source path 或 URL。
9. 在 `## Evidence Used` 中标注 prompt 列出的页面是 `used` 还是 `not used - reason`，并列出混合探索中额外使用的页面或 web 来源。

## 分层检索策略

- `direct`：只使用直接关键词/向量命中。适合单点事实查询。
- `graph`：direct hits 加上 `.cwiki/graph/graph.json` 中的入边/出边邻居。适合可能需要附近概念、角色、模块或实体的问题。
- `path`：direct hits、图谱邻居，以及 top hits 之间的最短路径证据。适合流程、机制、依赖、关系、how/why 问题。
- `synthesis`：direct、graph、path，加上 `overview.md`、`synthesis.md` 和中心节点。适合综合总结、对比、取舍、策略和评估。
- `auto`：由 CLI 根据问题自动选择层级。如果 `auto` 选到 `path` 但没有路径证据，会回退到 `graph`，并在 Retrieval Trace 记录原因。

图检索不是把图谱当事实来源，而是把 link graph 当导航层。当前 graph 不是 typed entity-relation graph。读取 Retrieval Trace 时：

- Direct Hits 是主证据。
- Graph-Expanded Pages 是邻近上下文。
- Path Evidence 解释页面之间的关系。
- Final Context Pages 是本次可复现证据包。

当语义重排值得额外调用一次模型时，可以运行 `cwiki ask . "<question>" --graph-rerank` 或 `cwiki answer . "<question>" --graph-rerank`。回答前读取 `LLM Graph Rerank` 区块，但事实依据仍以页面正文、Claim Ledger 和 source path 为准。

## 本地配置

- `.env.example` 记录本地模型与 web-search 默认配置。
- 使用 `cwiki answer` 前，把 `.env.example` 复制为 `.env` 并填入 provider/API key。
- `.env` 被 git 忽略，不应提交。
- `.env` 只影响终端/CLI 工作流，例如 `cwiki answer`；不会改变当前 agent 平台正在使用的聊天模型。
- `web-ask` 会读取 `.env` 中的 wiki/web 权重和来源数量默认值，但命令行参数优先。
- 如果答案或评估指出缺少案例、量化指标、最新事实、迁移/实施指南等外部证据，运行 `cwiki eval-answer . <answer-file> --web-on-gaps` 或 `cwiki answer . "<question>" --web-on-gaps`，生成 `.cwiki/web-gaps/`、web research、web capture checklist 和 fusion prompt 产物。
- `--web-on-gaps` 使用同一组 `CWIKI_WEB_*` 默认值，也支持 `--web-gap-max-sources`、`--web-gap-wiki-weight`、`--web-gap-web-weight` 单次覆盖。
- CLI 会把 `answer`、图重排和 `--llm` evaluation 的模型用量自动记录到 `.cwiki/usage/llm-usage.jsonl`。
- 如果当前 agent 平台能显示 ingest、update、浏览器研究、最终回答或其它平台模型工作的 token/费用，用 `cwiki usage-log . --operation <step> --provider agent-platform --model <visible-model-name> ...` 手动补记。
- 需要完整成本报告时运行 `cwiki usage-report .`；可用 `--operation`、`--artifact`、`--question`、`--provider`、`--model`、`--since`、`--until` 过滤。
- 对 agent 平台中的 LLM-assisted evaluation，应使用当前 agent 模型，而不是 `.env` 模型。先把辅助评估写到 `.cwiki/eval/agent-assisted-*.md`，再用 `--agent-eval-file <file> --agent-model <visible-model-name>` 附加进正式报告。

## 操作原则

- 优先更新已有 wiki 页面，避免创建孤立页面。
- 生成知识应保存到合适的 `wiki/` 分区，不要放到顶层临时文件夹。
- 使用 `[[slug]]` wikilinks 建立交叉引用。
- 每个事实性 claim 都需要 source path 或 URL。
- 保持源语言：中文来源生成中文 wiki 页面，英文来源生成英文 wiki 页面。除非用户要求，不要默认翻译。
- 保留矛盾和不确定性，不要静默抹掉。
- `wiki/overview.md` 和 `wiki/synthesis.md` 是两个可选第一阅读面，不是占位页。
- 每次 ingest 或 update 后都刷新 `overview.md` 与 `synthesis.md`。
- 有价值的问答应建议沉淀到 `wiki/synthesis.md`、`wiki/comparisons/` 或其它合适页面。
- web evidence 在 capture 前仍是外部证据；引用精确 URL 和访问日期，重要来源先 `cwiki capture` 再摄入，并同步维护 `.cwiki/web-captures/`。
- 大幅更新页面或链接后，运行 `cwiki link-graph-report .` 刷新 link graph。
- 周期性运行 `cwiki lint .` 检查断链、过期 claim 和孤立页面。
