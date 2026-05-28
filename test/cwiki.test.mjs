import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, readFile, readdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const exec = promisify(execFile);
const cli = path.resolve("bin/cwiki.mjs");

async function run(args, options = {}) {
  return exec(process.execPath, [cli, ...args], {
    cwd: path.resolve("."),
    ...options
  });
}

test("init creates a usable wiki", async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), "cwiki-"));
  await run(["init", dir, "--domain", "Test knowledge"]);

  assert.equal(existsSync(path.join(dir, "WIKI_SCHEMA.md")), true);
  assert.equal(existsSync(path.join(dir, "CLAUDE.md")), true);
  assert.equal(existsSync(path.join(dir, "AGENTS.md")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "index.md")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "hot.md")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "stale.md")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "overview.md")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "synthesis.md")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "summaries")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "entities")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "concepts")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "comparisons")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "lessons")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "indexes")), true);
  assert.equal(existsSync(path.join(dir, "wiki", "logs")), true);
  assert.equal(existsSync(path.join(dir, ".claude", "skills", "wiki-init", "SKILL.md")), true);
  assert.equal(existsSync(path.join(dir, ".agents", "skills", "wiki-ingest", "SKILL.md")), true);
  assert.equal(existsSync(path.join(dir, ".claude", "skills", "wiki-agent-browser", "SKILL.md")), true);
  assert.equal(existsSync(path.join(dir, ".claude", "skills", "wiki-dream", "SKILL.md")), true);
  assert.equal(existsSync(path.join(dir, ".cwiki", "manifest.json")), true);

  const schema = await readFile(path.join(dir, "WIKI_SCHEMA.md"), "utf8");
  assert.match(schema, /Domain: Test knowledge/);
  const claude = await readFile(path.join(dir, "CLAUDE.md"), "utf8");
  assert.match(claude, /Domain: Test knowledge/);
  assert.match(claude, /The human owns `raw\/`; the LLM owns `wiki\/`/);
});

test("index lists generated wiki sections", async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), "cwiki-"));
  await run(["init", dir, "--domain", "Index test"]);

  await writeFile(path.join(dir, "wiki", "concepts", "retrieval.md"), `---
title: Retrieval
kind: concept
tags: [ai]
sources: 1
updated: 2026-05-08
status: active
---

# Retrieval

Finding relevant evidence.
`, "utf8");

  await writeFile(path.join(dir, "wiki", "comparisons", "rag-vs-llm-wiki.md"), `---
title: RAG vs LLM Wiki
kind: comparison
tags: [analysis]
sources: 1
updated: 2026-05-08
---

# RAG vs LLM Wiki
`, "utf8");

  await run(["index", dir]);
  const index = await readFile(path.join(dir, "wiki", "index.md"), "utf8");
  assert.match(index, /\[\[retrieval\]\]/);
  assert.match(index, /\[\[rag-vs-llm-wiki\]\]/);
  assert.match(index, /Concept Pages/);
  assert.match(index, /Comparisons/);
});

test("lint reports broken links", async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), "cwiki-"));
  await run(["init", dir, "--domain", "Lint test"]);

  await writeFile(path.join(dir, "wiki", "concepts", "a.md"), `---
title: A
kind: concept
tags: [test]
sources: 1
updated: 2026-05-08
---

# A

Links to [[missing-page]].
`, "utf8");

  await assert.rejects(run(["lint", dir]), /Command failed/);
});

test("lint ignores wikilinks inside code spans", async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), "cwiki-"));
  await run(["init", dir, "--domain", "Code link test"]);

  await writeFile(path.join(dir, "wiki", "concepts", "code-example.md"), `---
title: Code Example
kind: concept
tags: [test]
sources: 1
updated: 2026-05-10
---

# Code Example

Inline code \`[[not-a-real-link]]\` should not count.

\`\`\`markdown
[[also-not-real]]
\`\`\`
`, "utf8");

  const result = await run(["lint", dir]);
  assert.match(result.stdout, /Broken links: 0/);
});

test("capture creates raw record and ingest prompt", async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), "cwiki-"));
  await run(["init", dir, "--domain", "Capture test"]);
  await run(["capture", dir, "https://example.com/some-article", "--title", "Some Article"]);

  const rawDir = path.join(dir, "raw", "captures");
  assert.equal(existsSync(rawDir), true);
  const prompts = await readdir(path.join(dir, ".cwiki", "prompts"));
  assert.equal(prompts.some((name) => /^ingest-\d{4}-\d{2}-\d{2}-some-article-[a-f0-9]{8}\.md$/.test(name)), true);
  assert.equal(existsSync(path.join(dir, ".cwiki", "sources", "source-manifest.jsonl")), true);
});
