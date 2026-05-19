---
name: wiki-query
description: Use when answering questions against the wiki.
---

# Wiki Query

Do not answer from memory first. The compiled wiki is the working source of truth.

## Steps

1. Prefer the standard path first: run `cwiki ask . "<question>" --retrieval auto` when no current query prompt exists, then read the generated `.cwiki/prompts/query-*.md` and `.cwiki/briefs/brief-*.md`.
2. Treat the generated query prompt as the reproducible evidence boundary. It tells you which pages were retrieved, which output shape to use, and how to report gaps.
3. Read Retrieval Trace before reading pages:
   - `direct` means direct hits are likely enough for narrow fact lookup.
   - `graph` means direct hits plus link-graph-expanded neighbors should be checked for nearby concepts, roles, modules, or entities. This is wikilink navigation, not typed knowledge-graph reasoning.
   - `path` means the answer should inspect shortest-path evidence for workflows, mechanisms, dependencies, or relationships.
   - `synthesis` means the answer should include overview/synthesis/central pages for broad comparison, strategy, evaluation, or summary questions.
   - If `--graph-rerank` was used, inspect the `LLM Graph Rerank` section and respect the reranked Final Context Pages order unless the page evidence contradicts it.
   - If `auto` fell back from `path` to `graph`, treat graph context as the active layer and state any weak/missing path evidence in `## Gaps`.
4. Read `wiki/index.md`.
5. Read relevant pages across `wiki/summaries/`, `wiki/entities/`, `wiki/concepts/`, `wiki/comparisons/`, `wiki/overview.md`, and `wiki/synthesis.md`.
6. If the generated prompt is incomplete, use the hybrid agent workflow: search the wiki again, inspect likely adjacent pages, and follow one level of relevant `[[wikilinks]]`.
7. If the wiki is insufficient, say what is missing and optionally use current web sources if the user requested or the claim is time-sensitive.
8. Answer with `## Evidence Used`, `## Answer`, and `## Gaps`.
9. Cite local pages like `[[topic]]` and keep source paths or URLs close to factual claims.
10. Offer to save substantial synthesis into the appropriate wiki location.
11. If the agent platform shows token or cost numbers for this platform-model answer, record them with `cwiki usage-log . --operation agent-answer --provider agent-platform --model <visible-model-name> ...`.

If the user accepts saving:

1. Update `wiki/synthesis.md`, create `wiki/comparisons/<slug>.md`, or create another fitting page under `wiki/`.
2. Run `cwiki index .`.
3. Run `cwiki link-graph-report .` after link changes.
4. Append to `wiki/log.md`.
