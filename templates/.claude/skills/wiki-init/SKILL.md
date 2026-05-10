---
name: wiki-init
description: Use when creating a new LLM Compound Wiki or reinitializing a wiki structure.
---

# Wiki Init

Initialize the wiki with:

```bash
cwiki init <target-dir> --domain "<domain>"
```

After initialization:

- read `WIKI_SCHEMA.md`
- ask the user what source types they expect to add
- recommend keeping private or copyrighted raw material out of git
- tell the user they can add files under `raw/` or run `cwiki capture . <file-or-url>`

Do not write domain pages until there is source material or explicit user guidance.
