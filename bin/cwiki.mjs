#!/usr/bin/env node

import { copyFile, mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, "..");
const templateRoot = path.join(projectRoot, "templates");
const wikiSections = ["summaries", "entities", "concepts", "comparisons"];
const ignoredWikiFiles = new Set(["index.md", "log.md"]);

const today = () => new Date().toISOString().slice(0, 10);

function usage() {
  return `LLM Compound Wiki

Usage:
  cwiki init <dir> [--domain "..."]
  cwiki index <dir>
  cwiki lint <dir>
  cwiki search <dir> <query>
  cwiki capture <dir> <file-or-url> [--title "..."]

Examples:
  cwiki init ./my-wiki --domain "AI research notes"
  cwiki capture . https://example.com/article --title "Example Article"
  cwiki search . "retrieval"
  cwiki lint .
`;
}

function parseOptions(args) {
  const opts = {};
  const rest = [];
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg.startsWith("--")) {
      const key = arg.slice(2);
      const next = args[i + 1];
      if (!next || next.startsWith("--")) {
        opts[key] = true;
      } else {
        opts[key] = next;
        i += 1;
      }
    } else {
      rest.push(arg);
    }
  }
  return { opts, rest };
}

async function ensureDir(dir) {
  await mkdir(dir, { recursive: true });
}

async function writeIfMissing(file, content) {
  if (existsSync(file)) return false;
  await ensureDir(path.dirname(file));
  await writeFile(file, content, "utf8");
  return true;
}

async function listMarkdownFiles(dir) {
  if (!existsSync(dir)) return [];
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listMarkdownFiles(full));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(full);
    }
  }
  return files.sort();
}

function slugify(input) {
  const ascii = input
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/https?:\/\//g, "")
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return ascii || "untitled";
}

function parseFrontmatter(text) {
  if (!text.startsWith("---\n")) return {};
  const end = text.indexOf("\n---", 4);
  if (end === -1) return {};
  const yaml = text.slice(4, end).trim().split(/\r?\n/);
  const result = {};
  for (const line of yaml) {
    const match = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (match) result[match[1]] = match[2].trim();
  }
  return result;
}

function extractTitle(text, fallback) {
  const fm = parseFrontmatter(text);
  if (fm.title) return fm.title.replace(/^["']|["']$/g, "");
  const heading = text.match(/^#\s+(.+)$/m);
  return heading ? heading[1].trim() : fallback;
}

function extractSummary(text) {
  const withoutFrontmatter = text.replace(/^---\n[\s\S]*?\n---\n?/, "");
  const lines = withoutFrontmatter
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && !line.startsWith("|") && !line.startsWith("- [["));
  return (lines[0] || "No summary yet.").replace(/\s+/g, " ").slice(0, 140);
}

function wikilinks(text) {
  const links = [];
  const searchable = text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`[^`\n]*`/g, "");
  const regex = /\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]/g;
  let match;
  while ((match = regex.exec(searchable))) {
    links.push(match[1].trim());
  }
  return links;
}

async function initWiki(target, opts) {
  const root = path.resolve(target);
  const domain = opts.domain || "Personal knowledge base";
  const date = today();

  await ensureDir(path.join(root, "raw"));
  await ensureDir(path.join(root, ".cwiki", "prompts"));
  for (const section of wikiSections) await ensureDir(path.join(root, "wiki", section));
  await ensureDir(path.join(root, ".claude", "skills"));
  await ensureDir(path.join(root, ".agents", "skills"));

  await writeIfMissing(path.join(root, "raw", ".gitkeep"), "");
  await writeIfMissing(path.join(root, ".cwiki", "prompts", ".gitkeep"), "");
  for (const section of wikiSections) await writeIfMissing(path.join(root, "wiki", section, ".gitkeep"), "");
  await writeIfMissing(path.join(root, ".gitignore"), "raw/**\n!raw/.gitkeep\n.cwiki/prompts/**\n!.cwiki/prompts/.gitkeep\n.DS_Store\n");

  const schema = await readFile(path.join(templateRoot, "WIKI_SCHEMA.md"), "utf8");
  const claude = await readFile(path.join(templateRoot, "CLAUDE.md"), "utf8");
  const agents = await readFile(path.join(templateRoot, "AGENTS.md"), "utf8");
  await writeIfMissing(path.join(root, "WIKI_SCHEMA.md"), schema.replaceAll("{{domain}}", domain).replaceAll("{{date}}", date));
  await writeIfMissing(path.join(root, "CLAUDE.md"), claude.replaceAll("{{domain}}", domain).replaceAll("{{date}}", date));
  await writeIfMissing(path.join(root, "AGENTS.md"), agents);

  await copySkills(root);
  await writeIfMissing(path.join(root, "wiki", "overview.md"), starterPage("Overview", "overview", domain, date));
  await writeIfMissing(path.join(root, "wiki", "synthesis.md"), starterPage("Synthesis", "synthesis", "Current cross-source synthesis. The LLM maintains this as the wiki matures.", date));
  await writeIfMissing(path.join(root, "wiki", "index.md"), renderIndex([]));
  await writeIfMissing(path.join(root, "wiki", "log.md"), `# Operation Log

Append-only, never modify history.

Format: \`## [YYYY-MM-DD] operation | title\`

---

## [${date}] init | ${domain}
- Created wiki structure
- Created CLAUDE.md, WIKI_SCHEMA.md, and AGENTS.md
- Initialized index and log
`);

  console.log(`Initialized LLM Compound Wiki at ${root}`);
  console.log(`Next: add sources to ${path.join(root, "raw")} or run cwiki capture ${root} <file-or-url>`);
}

function starterPage(title, kind, summary, date) {
  return `---
title: ${title}
kind: ${kind}
tags: [${kind}]
sources: 0
updated: ${date}
status: active
---

# ${title}

${summary}
`;
}

async function copySkills(root) {
  for (const namespace of [".claude", ".agents"]) {
    const skillsRoot = path.join(templateRoot, namespace, "skills");
    const skillNames = existsSync(skillsRoot) ? await readdir(skillsRoot) : [];
    for (const name of skillNames) {
      const source = path.join(skillsRoot, name, "SKILL.md");
      const dest = path.join(root, namespace, "skills", name, "SKILL.md");
      if (existsSync(source)) {
        await ensureDir(path.dirname(dest));
        if (!existsSync(dest)) await copyFile(source, dest);
      }
    }
  }
}

async function collectPages(root) {
  const wikiDir = path.join(root, "wiki");
  const wikiFiles = (await listMarkdownFiles(wikiDir))
    .filter((file) => !ignoredWikiFiles.has(path.basename(file)));
  const load = async (file) => {
    const text = await readFile(file, "utf8");
    const slug = path.basename(file, ".md");
    const fm = parseFrontmatter(text);
    const rel = path.relative(root, file);
    const section = sectionForFile(root, file);
    return {
      file,
      rel,
      slug,
      section,
      kind: (fm.kind || section || "wiki").replace(/^["']|["']$/g, ""),
      text,
      title: extractTitle(text, slug),
      summary: extractSummary(text),
      tags: fm.tags || "",
      updated: fm.updated || "",
      status: fm.status || "",
      links: wikilinks(text)
    };
  };
  return Promise.all(wikiFiles.map((file) => load(file)));
}

function sectionForFile(root, file) {
  const rel = path.relative(path.join(root, "wiki"), file);
  const parts = rel.split(path.sep);
  return parts.length > 1 ? parts[0] : "root";
}

function renderIndex(pages) {
  const bySection = new Map();
  for (const page of pages) {
    if (!bySection.has(page.section)) bySection.set(page.section, []);
    bySection.get(page.section).push(page);
  }

  const labels = [
    ["root", "Overview And Synthesis"],
    ["summaries", "Summaries"],
    ["entities", "Entity Pages"],
    ["concepts", "Concept Pages"],
    ["comparisons", "Comparisons"]
  ];

  const sections = labels.map(([key, label]) => {
    const rows = bySection.get(key) || [];
    const body = rows.length
      ? rows.map((page) => `| [[${page.slug}]] | ${escapeCell(page.title)} | ${escapeCell(page.summary)} | ${escapeCell(page.tags)} | ${page.updated || "-"} | ${page.rel} |`).join("\n")
      : "| (None yet) | - | - | - | - | - |";
    return `## ${label}

| Page | Title | Summary | Tags | Last Updated | File |
|---|---|---|---|---|---|
${body}`;
  }).join("\n\n");

  return `# Index

The wiki layer is fully owned by the LLM. It contains generated summaries, entity pages, concept pages, comparisons, an overview, and a synthesis.

${sections}

## Cross-Reference Notes

Generated from page wikilinks by agents as needed.
`;
}

function escapeCell(value) {
  return String(value || "-").replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
}

async function indexWiki(target) {
  const root = path.resolve(target);
  assertWiki(root);
  const pages = await collectPages(root);
  await writeFile(path.join(root, "wiki", "index.md"), renderIndex(pages), "utf8");
  console.log(`Indexed ${pages.length} wiki pages across ${new Set(pages.map((page) => page.section)).size} sections.`);
}

async function lintWiki(target) {
  const root = path.resolve(target);
  assertWiki(root);
  const pages = await collectPages(root);
  const known = new Set(pages.map((page) => page.slug));
  const inbound = new Map(pages.map((page) => [page.slug, 0]));
  const broken = [];
  const missingFrontmatter = [];
  const stale = [];

  for (const page of pages) {
    const fm = parseFrontmatter(page.text);
    const missing = ["title", "tags", "sources", "updated"].filter((key) => !fm[key]);
    if (missing.length) missingFrontmatter.push({ page, missing });

    if (isStale(page)) stale.push(page);

    for (const link of page.links) {
      if (!known.has(link)) broken.push({ from: page.slug, to: link });
      if (inbound.has(link)) inbound.set(link, inbound.get(link) + 1);
    }
  }

  const orphan = [...inbound.entries()]
    .filter(([, count]) => count === 0)
    .map(([slug]) => slug)
    .filter((slug) => !["overview", "synthesis"].includes(slug))
    .filter((slug) => pages.length > 1 || slug !== pages[0]?.slug);

  const report = {
    pages: pages.length,
    broken,
    missingFrontmatter,
    orphan,
    stale
  };

  printLint(report);
  if (broken.length || missingFrontmatter.length) process.exitCode = 1;
}

function isStale(page) {
  if (!page.updated) return false;
  if (!/\b(latest|current|recent|state-of-the-art|最新|当前|近期)\b/i.test(page.text)) return false;
  const updated = new Date(page.updated.replace(/^["']|["']$/g, ""));
  if (Number.isNaN(updated.getTime())) return false;
  const ageDays = (Date.now() - updated.getTime()) / 86400000;
  return ageDays > 90;
}

function printLint(report) {
  console.log(`# Lint Report`);
  console.log(`Pages: ${report.pages}`);
  console.log(`Broken links: ${report.broken.length}`);
  console.log(`Missing frontmatter: ${report.missingFrontmatter.length}`);
  console.log(`Orphan pages: ${report.orphan.length}`);
  console.log(`Stale pages: ${report.stale.length}`);

  if (report.broken.length) {
    console.log(`\n## Broken Links`);
    for (const item of report.broken) console.log(`- [[${item.from}]] -> [[${item.to}]]`);
  }
  if (report.missingFrontmatter.length) {
    console.log(`\n## Missing Frontmatter`);
    for (const item of report.missingFrontmatter) console.log(`- [[${item.page.slug}]] missing ${item.missing.join(", ")}`);
  }
  if (report.orphan.length) {
    console.log(`\n## Orphan Pages`);
    for (const slug of report.orphan) console.log(`- [[${slug}]]`);
  }
  if (report.stale.length) {
    console.log(`\n## Stale Pages`);
    for (const page of report.stale) console.log(`- [[${page.slug}]] last updated ${page.updated}`);
  }
}

async function searchWiki(target, query) {
  const root = path.resolve(target);
  assertWiki(root);
  const q = query.toLowerCase();
  const pages = await collectPages(root);
  const hits = pages
    .map((page) => {
      const haystack = `${page.title}\n${page.summary}\n${page.text}`.toLowerCase();
      const count = haystack.split(q).length - 1;
      return { page, count };
    })
    .filter((hit) => hit.count > 0)
    .sort((a, b) => b.count - a.count || a.page.slug.localeCompare(b.page.slug))
    .slice(0, 20);

  if (!hits.length) {
    console.log(`No matches for "${query}".`);
    return;
  }
  for (const hit of hits) {
    console.log(`- [[${hit.page.slug}]] (${hit.count}) ${hit.page.rel}`);
    console.log(`  ${hit.page.summary}`);
  }
}

async function captureSource(target, source, opts) {
  const root = path.resolve(target);
  assertWiki(root);
  const title = opts.title || inferTitle(source);
  const slug = slugify(title);
  const date = today();
  const isUrl = /^https?:\/\//i.test(source);
  const rawDir = path.join(root, "raw", "captures");
  await ensureDir(rawDir);
  const rawFile = path.join(rawDir, `${date}-${slug}.md`);

  let body;
  if (isUrl) {
    body = `---
title: ${title}
source: ${source}
captured: ${date}
type: url
---

# ${title}

Source URL: ${source}

Agent instruction: fetch this URL, read it in full, and compile it into the wiki using WIKI_SCHEMA.md.
`;
  } else {
    const absolute = path.resolve(source);
    const stats = await stat(absolute);
    if (!stats.isFile()) throw new Error(`Not a file: ${absolute}`);
    const text = await readFile(absolute, "utf8");
    body = `---
title: ${title}
source: ${absolute}
captured: ${date}
type: file
---

# ${title}

Original file: ${absolute}

## Content

${text}
`;
  }

  await writeFile(rawFile, body, "utf8");
  const promptFile = path.join(root, ".cwiki", "prompts", `ingest-${date}-${slug}.md`);
  await writeFile(promptFile, `---
title: Ingest Prompt - ${title}
tags: [ingest, prompt]
sources: 1
updated: ${date}
status: pending
---

# Ingest Prompt - ${title}

Read \`${path.relative(root, rawFile)}\` in full and compile it into this wiki.

Follow \`WIKI_SCHEMA.md\`:

1. Read \`wiki/index.md\`.
2. Identify existing summaries, entities, concepts, comparisons, overview, or synthesis pages to update.
3. Extract source-backed claims into claim ledgers.
4. Add bidirectional wikilinks where appropriate.
5. Run \`cwiki index .\`.
6. Append to \`wiki/log.md\`.
`, "utf8");

  console.log(`Captured source: ${path.relative(root, rawFile)}`);
  console.log(`Created ingest prompt: ${path.relative(root, promptFile)}`);
}

function inferTitle(source) {
  if (/^https?:\/\//i.test(source)) {
    const url = new URL(source);
    const last = url.pathname.split("/").filter(Boolean).pop() || url.hostname;
    return last.replace(/\.[A-Za-z0-9]+$/, "").replace(/[-_]+/g, " ");
  }
  return path.basename(source, path.extname(source)).replace(/[-_]+/g, " ");
}

function assertWiki(root) {
  if (!existsSync(path.join(root, "wiki")) || !existsSync(path.join(root, "WIKI_SCHEMA.md"))) {
    throw new Error(`Not an LLM Compound Wiki: ${root}\nRun: cwiki init ${root}`);
  }
}

async function main() {
  const [cmd, ...args] = process.argv.slice(2);
  if (!cmd || cmd === "-h" || cmd === "--help") {
    console.log(usage());
    return;
  }

  const { opts, rest } = parseOptions(args);
  if (cmd === "init") {
    if (!rest[0]) throw new Error("Missing target directory.");
    await initWiki(rest[0], opts);
  } else if (cmd === "index") {
    if (!rest[0]) throw new Error("Missing wiki directory.");
    await indexWiki(rest[0]);
  } else if (cmd === "lint") {
    if (!rest[0]) throw new Error("Missing wiki directory.");
    await lintWiki(rest[0]);
  } else if (cmd === "search") {
    if (!rest[0] || !rest[1]) throw new Error("Usage: cwiki search <dir> <query>");
    await searchWiki(rest[0], rest.slice(1).join(" "));
  } else if (cmd === "capture") {
    if (!rest[0] || !rest[1]) throw new Error("Usage: cwiki capture <dir> <file-or-url>");
    await captureSource(rest[0], rest[1], opts);
  } else {
    throw new Error(`Unknown command: ${cmd}\n\n${usage()}`);
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
