---
name: wiki-lint
description: Use when checking wiki health, fixing broken links, stale claims, orphan pages, or missing metadata.
---

# Wiki Lint

Run:

```bash
cwiki lint .
```

Review:

- broken links
- missing frontmatter
- orphan pages
- stale pages with words like "latest", "current", or "recent"
- misplaced pages, such as entity pages under `wiki/concepts/`

When fixing:

- show the intended edits before applying them
- cite a source for factual changes
- prefer adding meaningful links over deleting pages
- preserve the intended wiki section structure from `WIKI_SCHEMA.md`
- append the maintenance action to `wiki/log.md`

After fixes, run `cwiki index .` and then `cwiki lint .` again.
