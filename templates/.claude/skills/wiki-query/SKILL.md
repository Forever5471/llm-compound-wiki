---
name: wiki-query
description: Use when answering questions against the wiki.
---

# Wiki Query

Do not answer from memory first. The compiled wiki is the working source of truth.

## Steps

1. Read `wiki/index.md`.
2. Read relevant pages across `wiki/summaries/`, `wiki/entities/`, `wiki/concepts/`, `wiki/comparisons/`, `wiki/overview.md`, and `wiki/synthesis.md`.
3. Follow one level of relevant `[[wikilinks]]`.
4. If the wiki is insufficient, say what is missing and optionally use current web sources if the user requested or the claim is time-sensitive.
5. Answer with local citations like `[[topic]]` and source paths or URLs.
6. Offer to save substantial synthesis into the appropriate wiki location.

If the user accepts saving:

1. Update `wiki/synthesis.md`, create `wiki/comparisons/<slug>.md`, or create another fitting page under `wiki/`.
2. Run `cwiki index .`.
3. Append to `wiki/log.md`.
