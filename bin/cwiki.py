#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib import error as urlerror
from urllib import request
from urllib.parse import urlparse
from xml.etree import ElementTree


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = PROJECT_ROOT / "templates"
WIKI_SECTIONS = ["summaries", "entities", "concepts", "comparisons"]
IGNORED_WIKI_FILES = {"index.md", "log.md"}
DEFAULT_TOP_K = 6
RETRIEVAL_MODES = {"auto", "direct", "graph", "path", "synthesis"}
DEFAULT_WIKI_WEIGHT = 0.6
DEFAULT_WEB_WEIGHT = 0.4
DEFAULT_OPENAI_MODEL = "gpt-5.2"
DEFAULT_GLM_MODEL = "glm-4.6v"
DEFAULT_GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_ENV_EXAMPLE = """CWIKI_PROVIDER=glm
CWIKI_GLM_MODEL=glm-4.6v
GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GLM_API_KEY=replace-with-your-local-key

# Optional OpenAI defaults
CWIKI_OPENAI_MODEL=gpt-5.2
OPENAI_API_KEY=replace-with-your-local-key

# Optional graph rerank defaults
# Used by `cwiki ask --graph-rerank` and `cwiki answer --graph-rerank`.
# If unset, graph rerank uses CWIKI_PROVIDER / CWIKI_MODEL defaults.
# GLM graph rerank disables thinking by default so output tokens go to strict JSON.
# CWIKI_GRAPH_RERANK_PROVIDER=glm
# CWIKI_GRAPH_RERANK_MODEL=glm-4.6v
# CWIKI_GRAPH_RERANK_API_KEY_ENV=GLM_API_KEY
# CWIKI_GRAPH_RERANK_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# CWIKI_GRAPH_RERANK_THINKING=disabled

# Optional token cost rates. Values are price per 1M tokens; no defaults are hardcoded.
# You can set generic, provider-level, or provider+model-level rates.
# For glm-4.6v, the model fragment is GLM_4_6V.
# CWIKI_COST_INPUT_PER_1M=0
# CWIKI_COST_OUTPUT_PER_1M=0
# CWIKI_COST_GLM_INPUT_PER_1M=0
# CWIKI_COST_GLM_OUTPUT_PER_1M=0
# CWIKI_COST_GLM_GLM_4_6V_INPUT_PER_1M=0
# CWIKI_COST_GLM_GLM_4_6V_OUTPUT_PER_1M=0
# CWIKI_COST_CURRENCY=USD

# web-ask defaults
CWIKI_WEB_WIKI_WEIGHT=0.6
CWIKI_WEB_WEIGHT=0.4
CWIKI_WEB_MAX_SOURCES=6
CWIKI_WEB_ENABLED=true
"""
STOPWORDS = {
    "a",
    "an",
    "and",
    "about",
    "does",
    "do",
    "is",
    "are",
    "the",
    "this",
    "that",
    "to",
    "of",
    "in",
    "on",
    "for",
    "what",
    "wiki",
    "know",
    "knows",
    "tell",
    "me",
    "什么",
    "这个",
    "一下",
    "关于",
    "知道",
    "了解",
    "结论",
    "如何",
}
SYNONYM_SEEDS = {
    "gray": ["灰区", "模糊", "仲裁"],
    "zone": ["区域", "灰区"],
    "gray_zone": ["灰区", "模糊样本", "仲裁"],
    "self": ["自动", "自主"],
    "healing": ["自愈", "恢复", "修复"],
    "rpa": ["自动化", "流程"],
    "llm": ["大模型", "模型"],
    "answer": ["问答", "回答"],
    "query": ["检索", "查询", "提问"],
    "capture": ["捕获", "摄入", "解析"],
    "自愈": ["self", "healing", "恢复", "修复"],
    "灰区": ["gray", "zone", "gray_zone", "模糊", "仲裁"],
    "仲裁": ["rerank", "re-ranker", "裁决", "判断"],
    "检索": ["search", "retrieval", "query", "召回"],
    "问答": ["answer", "qa", "回答"],
    "摄入": ["capture", "ingest", "解析"],
}
VECTOR_DIMENSIONS = 128


@dataclass
class Page:
    file: Path
    rel: str
    slug: str
    section: str
    kind: str
    text: str
    title: str
    summary: str
    tags: str
    updated: str
    status: str
    links: list[str]


@dataclass
class LLMResponse:
    text: str
    usage: dict[str, object]
    cost: dict[str, object]


def today() -> str:
    return dt.date.today().isoformat()


def timestamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def load_local_env(root: Path) -> None:
    for env_file in (PROJECT_ROOT / ".env", Path.cwd() / ".env", root / ".env"):
        load_dotenv(env_file)


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError as error:
        raise RuntimeError(f"Invalid float for {name}: {value}") from error


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as error:
        raise RuntimeError(f"Invalid integer for {name}: {value}") from error


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    raise RuntimeError(f"Invalid boolean for {name}: {value}")


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    return True


def env_example_content() -> str:
    source = PROJECT_ROOT / ".env.example"
    if source.exists():
        return source.read_text(encoding="utf-8")
    return DEFAULT_ENV_EXAMPLE


def list_markdown_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(file for file in path.rglob("*.md") if file.is_file())


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    stripped = re.sub(r"https?://", "", stripped.lower())
    stripped = re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", "-", stripped)
    stripped = stripped.strip("-")[:80]
    return stripped or "untitled"


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].strip().splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            result[match.group(1)] = match.group(2).strip()
    return result


def clean_quoted(value: str) -> str:
    return re.sub(r"^[\"']|[\"']$", "", value)


def extract_title(text: str, fallback: str) -> str:
    frontmatter = parse_frontmatter(text)
    if frontmatter.get("title"):
        return clean_quoted(frontmatter["title"])
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def extract_summary(text: str) -> str:
    body = re.sub(r"^---\n[\s\S]*?\n---\n?", "", text)
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("|") or line.startswith("- [["):
            continue
        return re.sub(r"\s+", " ", line)[:140]
    return "No summary yet."


def wikilinks(text: str) -> list[str]:
    searchable = re.sub(r"```[\s\S]*?```", "", text)
    searchable = re.sub(r"`[^`\n]*`", "", searchable)
    pattern = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
    return [match.group(1).strip() for match in pattern.finditer(searchable)]


def starter_page(title: str, kind: str, summary: str, date: str) -> str:
    return f"""---
title: {title}
kind: {kind}
tags: [{kind}]
sources: 0
updated: {date}
status: active
---

# {title}

{summary}
"""


def starter_overview_page(domain: str, date: str) -> str:
    return f"""---
title: Overview
kind: overview
tags: [overview, map]
sources: 0
updated: {date}
status: seed
---

# Overview

This page is the wiki's durable map for **{domain}**. Use it as the first reading surface while the wiki is still growing; switch to [[synthesis]] first once there is enough source-backed cross-page judgment.

## Entry Decision

- Start here when you need orientation, topic boundaries, or the current page map.
- Start with [[synthesis]] when you need the current integrated thesis or a decision-ready answer.

## Current Map

- `wiki/summaries/` - source and topic summaries.
- `wiki/entities/` - people, organizations, products, projects, places, and named systems.
- `wiki/concepts/` - reusable ideas, methods, mechanisms, and terms.
- `wiki/comparisons/` - tradeoffs, alternatives, decision matrices, and conflicts.

## Navigation Seeds

- Add the most important pages here after each meaningful ingest.
- Prefer 5-9 high-signal links over a complete duplicate of `wiki/index.md`.
- Keep each link annotated with why a reader or agent should open it.

## Open Map Questions

- Which topics are central enough to become entry points?
- Which pages should be merged, split, or promoted into synthesis?
"""


def starter_synthesis_page(domain: str, date: str) -> str:
    return f"""---
title: Synthesis
kind: synthesis
tags: [synthesis, thesis]
sources: 0
updated: {date}
status: seed
---

# Synthesis

This page is the wiki's integrated thesis for **{domain}**. It should become the first reading surface only after the wiki contains enough source-backed pages to support cross-source judgment. Until then, use [[overview]] as the entry point.

## Current Thesis

No source-backed thesis has been promoted yet. When evidence accumulates, replace this seed text with the wiki's best current answer to: what do these sources collectively imply?

## Stable Claims

- Add only claims that are supported by wiki pages, source paths, URLs, or Claim Ledger rows.

## Tensions And Contradictions

- Keep unresolved contradictions visible instead of silently choosing a winner.

## Update Triggers

- New evidence changes the global interpretation.
- Several topic pages now support one reusable conclusion.
- A query answer is valuable enough to preserve as durable wiki knowledge.
"""


def copy_skills(root: Path) -> None:
    for namespace in [".claude", ".agents"]:
        skills_root = TEMPLATE_ROOT / namespace / "skills"
        if not skills_root.exists():
            continue
        for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
            source = skill_dir / "SKILL.md"
            dest = root / namespace / "skills" / skill_dir.name / "SKILL.md"
            if source.exists() and not dest.exists():
                ensure_dir(dest.parent)
                shutil.copyfile(source, dest)


def init_wiki(target: str, domain: str | None) -> None:
    root = Path(target).resolve()
    wiki_domain = domain or "Personal knowledge base"
    date = today()

    ensure_dir(root / "raw")
    ensure_dir(root / ".cwiki" / "prompts")
    for section in WIKI_SECTIONS:
        ensure_dir(root / "wiki" / section)
    ensure_dir(root / ".claude" / "skills")
    ensure_dir(root / ".agents" / "skills")

    write_if_missing(root / "raw" / ".gitkeep", "")
    write_if_missing(root / ".cwiki" / "prompts" / ".gitkeep", "")
    for section in WIKI_SECTIONS:
        write_if_missing(root / "wiki" / section / ".gitkeep", "")
    write_if_missing(
        root / ".gitignore",
        (
            "raw/**\n"
            "!raw/.gitkeep\n"
            ".cwiki/prompts/**\n"
            "!.cwiki/prompts/.gitkeep\n"
            ".cwiki/briefs/**\n"
            ".cwiki/answers/**\n"
            ".cwiki/web-research/**\n"
            ".cwiki/web-gaps/**\n"
            ".cwiki/eval/**\n"
            ".cwiki/graph/**\n"
            ".cwiki/usage/**\n"
            ".env\n"
            ".DS_Store\n"
        ),
    )

    replacements = {"{{domain}}": wiki_domain, "{{date}}": date}
    for template_name in ["WIKI_SCHEMA.md", "CLAUDE.md", "CLAUDE.zh-CN.md"]:
        content = (TEMPLATE_ROOT / template_name).read_text(encoding="utf-8")
        for key, value in replacements.items():
            content = content.replace(key, value)
        write_if_missing(root / template_name, content)
    write_if_missing(root / "AGENTS.md", (TEMPLATE_ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    write_if_missing(root / "AGENTS.zh-CN.md", (TEMPLATE_ROOT / "AGENTS.zh-CN.md").read_text(encoding="utf-8"))
    write_if_missing(root / ".env.example", env_example_content())

    copy_skills(root)
    write_if_missing(root / "wiki" / "overview.md", starter_overview_page(wiki_domain, date))
    write_if_missing(root / "wiki" / "synthesis.md", starter_synthesis_page(wiki_domain, date))
    write_if_missing(root / "wiki" / "index.md", render_index([]))
    write_if_missing(
        root / "wiki" / "log.md",
        f"""# Operation Log

Append-only, never modify history.

Format: `## [YYYY-MM-DD] operation | title`

---

## [{date}] init | {wiki_domain}
- Created wiki structure
- Created CLAUDE.md, CLAUDE.zh-CN.md, WIKI_SCHEMA.md, AGENTS.md, and AGENTS.zh-CN.md
- Created .env.example for local model and web-search defaults
- Initialized index and log
""",
    )

    print(f"Initialized LLM Compound Wiki at {root}")
    print("Config: copy .env.example to .env and add your provider/API keys when you want `cwiki answer` or web defaults.")
    print(f"Next: add sources to {root / 'raw'} or run cwiki capture {root} <file-or-url>")


def section_for_file(root: Path, file: Path) -> str:
    rel = file.relative_to(root / "wiki")
    return rel.parts[0] if len(rel.parts) > 1 else "root"


def collect_pages(root: Path) -> list[Page]:
    wiki_dir = root / "wiki"
    files = [file for file in list_markdown_files(wiki_dir) if file.name not in IGNORED_WIKI_FILES]
    pages: list[Page] = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        slug = file.stem
        frontmatter = parse_frontmatter(text)
        section = section_for_file(root, file)
        pages.append(
            Page(
                file=file,
                rel=file.relative_to(root).as_posix(),
                slug=slug,
                section=section,
                kind=clean_quoted(frontmatter.get("kind", section or "wiki")),
                text=text,
                title=extract_title(text, slug),
                summary=extract_summary(text),
                tags=frontmatter.get("tags", ""),
                updated=frontmatter.get("updated", ""),
                status=frontmatter.get("status", ""),
                links=wikilinks(text),
            )
        )
    return pages


def escape_cell(value: str) -> str:
    return (value or "-").replace("|", "\\|").replace("\n", " ")


def render_index(pages: list[Page]) -> str:
    by_section: dict[str, list[Page]] = {}
    for page in pages:
        by_section.setdefault(page.section, []).append(page)

    labels = [
        ("root", "Overview And Synthesis"),
        ("summaries", "Summaries"),
        ("entities", "Entity Pages"),
        ("concepts", "Concept Pages"),
        ("comparisons", "Comparisons"),
    ]

    rendered_sections: list[str] = []
    for key, label in labels:
        rows = by_section.get(key, [])
        if rows:
            body = "\n".join(
                f"| [[{page.slug}]] | {escape_cell(page.title)} | {escape_cell(page.summary)} | "
                f"{escape_cell(page.tags)} | {page.updated or '-'} | {page.rel} |"
                for page in rows
            )
        else:
            body = "| (None yet) | - | - | - | - | - |"
        rendered_sections.append(
            f"""## {label}

| Page | Title | Summary | Tags | Last Updated | File |
|---|---|---|---|---|---|
{body}"""
        )

    return f"""# Index

The wiki layer is fully owned by the LLM. It contains generated summaries, entity pages, concept pages, comparisons, an overview, and a synthesis.

{chr(10).join(rendered_sections)}

## Cross-Reference Notes

Generated from page wikilinks by agents as needed.
"""


def assert_wiki(root: Path) -> None:
    if not (root / "wiki").exists() or not (root / "WIKI_SCHEMA.md").exists():
        raise RuntimeError(f"Not an LLM Compound Wiki: {root}\nRun: cwiki init {root}")


def index_wiki(target: str) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    pages = collect_pages(root)
    (root / "wiki" / "index.md").write_text(render_index(pages), encoding="utf-8")
    sections = {page.section for page in pages}
    print(f"Indexed {len(pages)} wiki pages across {len(sections)} sections.")


def is_stale(page: Page) -> bool:
    if not page.updated:
        return False
    if not re.search(r"\b(latest|current|recent|state-of-the-art|最新|当前|近期)\b", page.text, flags=re.IGNORECASE):
        return False
    try:
        updated = dt.date.fromisoformat(clean_quoted(page.updated))
    except ValueError:
        return False
    return (dt.date.today() - updated).days > 90


def print_lint(report: dict[str, object]) -> None:
    broken = report["broken"]
    missing_frontmatter = report["missing_frontmatter"]
    orphan = report["orphan"]
    stale = report["stale"]

    print("# Lint Report")
    print(f"Pages: {report['pages']}")
    print(f"Broken links: {len(broken)}")
    print(f"Missing frontmatter: {len(missing_frontmatter)}")
    print(f"Orphan pages: {len(orphan)}")
    print(f"Stale pages: {len(stale)}")

    if broken:
        print("\n## Broken Links")
        for item in broken:
            print(f"- [[{item['from']}]] -> [[{item['to']}]]")
    if missing_frontmatter:
        print("\n## Missing Frontmatter")
        for item in missing_frontmatter:
            print(f"- [[{item['page'].slug}]] missing {', '.join(item['missing'])}")
    if orphan:
        print("\n## Orphan Pages")
        for slug in orphan:
            print(f"- [[{slug}]]")
    if stale:
        print("\n## Stale Pages")
        for page in stale:
            print(f"- [[{page.slug}]] last updated {page.updated}")


def lint_wiki(target: str) -> int:
    root = Path(target).resolve()
    assert_wiki(root)
    pages = collect_pages(root)
    known = {page.slug for page in pages}
    inbound = {page.slug: 0 for page in pages}
    broken: list[dict[str, str]] = []
    missing_frontmatter: list[dict[str, object]] = []
    stale: list[Page] = []

    for page in pages:
        frontmatter = parse_frontmatter(page.text)
        missing = [key for key in ["title", "tags", "sources", "updated"] if not frontmatter.get(key)]
        if missing:
            missing_frontmatter.append({"page": page, "missing": missing})
        if is_stale(page):
            stale.append(page)
        for link in page.links:
            if link not in known:
                broken.append({"from": page.slug, "to": link})
            if link in inbound:
                inbound[link] += 1

    orphan = [
        slug
        for slug, count in inbound.items()
        if count == 0 and slug not in {"overview", "synthesis"} and (len(pages) > 1 or slug != pages[0].slug)
    ]

    report = {
        "pages": len(pages),
        "broken": broken,
        "missing_frontmatter": missing_frontmatter,
        "orphan": orphan,
        "stale": stale,
    }
    print_lint(report)
    return 1 if broken or missing_frontmatter else 0


def eval_wiki(
    target: str,
    output: str | None = None,
    no_write: bool = False,
    json_output: bool = False,
    llm: bool = False,
    provider: str | None = None,
    model: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    max_output_tokens: int = 1000,
    agent_eval_file: str | None = None,
    agent_model: str | None = None,
) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    pages = collect_pages(root)
    result = build_wiki_eval(root, pages)
    attach_llm_eval(root, result, llm, provider, model, api_key_env, base_url, max_output_tokens, agent_eval_file, agent_model)
    report = render_eval_json(result) if json_output else render_wiki_eval_report(root, result)
    print(report)

    if no_write:
        return

    report_file = Path(output).resolve() if output else default_eval_report_path(root, "wiki-eval", "json" if json_output else "md")
    ensure_dir(report_file.parent)
    report_file.write_text(report, encoding="utf-8")
    update_eval_index(root, report_file, result)
    print(
        f"\nSaved evaluation report: {display_path(report_file, root)}",
        file=sys.stderr if json_output else sys.stdout,
    )


def eval_answer(
    target: str,
    answer: str,
    output: str | None = None,
    no_write: bool = False,
    json_output: bool = False,
    llm: bool = False,
    provider: str | None = None,
    model: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    max_output_tokens: int = 1000,
    agent_eval_file: str | None = None,
    agent_model: str | None = None,
    web_on_gaps: bool = False,
    web_gap_top_k: int = DEFAULT_TOP_K,
    web_gap_max_sources: int | None = None,
    web_gap_wiki_weight: float | None = None,
    web_gap_web_weight: float | None = None,
) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    answer_file = resolve_answer_file(root, answer)
    pages = collect_pages(root)
    result = build_answer_eval(root, answer_file, pages)
    attach_llm_eval(root, result, llm, provider, model, api_key_env, base_url, max_output_tokens, agent_eval_file, agent_model)
    if web_on_gaps:
        result["web_followup"] = create_web_followup_for_answer_gaps(
            root,
            answer_file,
            result,
            web_gap_top_k,
            web_gap_max_sources,
            web_gap_wiki_weight,
            web_gap_web_weight,
        )
    report = render_eval_json(result) if json_output else render_answer_eval_report(root, result)
    print(report)

    if no_write:
        return

    report_file = Path(output).resolve() if output else default_eval_report_path(root, "answer-eval", "json" if json_output else "md")
    ensure_dir(report_file.parent)
    report_file.write_text(report, encoding="utf-8")
    update_eval_index(root, report_file, result)
    print(
        f"\nSaved evaluation report: {display_path(report_file, root)}",
        file=sys.stderr if json_output else sys.stdout,
    )


def eval_all(
    target: str,
    answer: str | None = None,
    output: str | None = None,
    no_write: bool = False,
    json_output: bool = False,
    wiki_only: bool = False,
    llm: bool = False,
    provider: str | None = None,
    model: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    max_output_tokens: int = 1000,
    agent_eval_file: str | None = None,
    agent_model: str | None = None,
) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    if answer and wiki_only:
        raise RuntimeError("Use either --answer or --wiki-only, not both.")
    pages = collect_pages(root)
    wiki_result = build_wiki_eval(root, pages)
    answer_file = resolve_eval_all_answer_file(root, answer, wiki_only)
    answer_result = build_answer_eval(root, answer_file, pages) if answer_file else None
    result = build_combined_eval(root, wiki_result, answer_result, answer_selection(root, answer, answer_file, wiki_only))
    attach_llm_eval(root, result, llm, provider, model, api_key_env, base_url, max_output_tokens, agent_eval_file, agent_model)
    report = render_eval_json(result) if json_output else render_combined_eval_report(root, result)
    print(report)

    if no_write:
        return

    report_file = Path(output).resolve() if output else default_eval_report_path(root, "combined-eval", "json" if json_output else "md")
    ensure_dir(report_file.parent)
    report_file.write_text(report, encoding="utf-8")
    update_eval_index(root, report_file, result)
    print(
        f"\nSaved evaluation report: {display_path(report_file, root)}",
        file=sys.stderr if json_output else sys.stdout,
    )


def configure_eval_schedule(
    target: str,
    every_days: int | None,
    disabled: bool,
    run_if_due: bool,
    answer: str | None,
    wiki_only: bool,
    json_output: bool,
    llm: bool,
    provider: str | None,
    model: str | None,
    api_key_env: str | None,
    base_url: str | None,
    max_output_tokens: int,
) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    config_file = eval_schedule_file(root)
    if disabled:
        config = read_eval_schedule(root)
        config["enabled"] = False
        write_eval_schedule(root, config)
        print(f"Disabled scheduled evaluation: {display_path(config_file, root)}")
        return
    if every_days is not None:
        if every_days < 1:
            raise RuntimeError("--every-days must be at least 1.")
        config = {
            "enabled": True,
            "every_days": every_days,
            "created_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_run": None,
            "mode": "eval-all",
            "answer": answer or "",
            "wiki_only": wiki_only,
            "json": json_output,
            "llm": llm,
            "provider": provider or "",
            "model": model or "",
            "api_key_env": api_key_env or "",
            "base_url": base_url or "",
            "max_output_tokens": max_output_tokens,
        }
        write_eval_schedule(root, config)
        print(f"Saved scheduled evaluation config: {display_path(config_file, root)}")
    if run_if_due:
        run_eval_schedule_if_due(root)


def eval_schedule_file(root: Path) -> Path:
    return root / ".cwiki" / "eval" / "schedule.json"


def read_eval_schedule(root: Path) -> dict[str, object]:
    path = eval_schedule_file(root)
    if not path.exists():
        raise RuntimeError("No scheduled evaluation config found. Run `cwiki eval-schedule . --every-days N` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def write_eval_schedule(root: Path, config: dict[str, object]) -> None:
    path = eval_schedule_file(root)
    ensure_dir(path.parent)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_eval_schedule_if_due(root: Path) -> None:
    config = read_eval_schedule(root)
    if not config.get("enabled", True):
        print("Scheduled evaluation is disabled.")
        return
    every_days = int(config.get("every_days", 0))
    if every_days < 1:
        raise RuntimeError("Invalid scheduled evaluation config: every_days must be at least 1.")
    last_run = config.get("last_run")
    if isinstance(last_run, str) and last_run:
        last = dt.datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S")
        next_run = last + dt.timedelta(days=every_days)
        if dt.datetime.now() < next_run:
            print(f"Scheduled evaluation is not due yet. Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            return
    eval_all(
        str(root),
        answer=str(config.get("answer") or "") or None,
        json_output=bool(config.get("json", False)),
        wiki_only=bool(config.get("wiki_only", False)),
        llm=bool(config.get("llm", False)),
        provider=str(config.get("provider") or "") or None,
        model=str(config.get("model") or "") or None,
        api_key_env=str(config.get("api_key_env") or "") or None,
        base_url=str(config.get("base_url") or "") or None,
        max_output_tokens=int(config.get("max_output_tokens", 1000)),
    )
    config["last_run"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_eval_schedule(root, config)


def build_wiki_eval(root: Path, pages: list[Page]) -> dict[str, object]:
    language = detect_report_language(pages)
    warnings: list[dict[str, str]] = []
    known = {page.slug for page in pages}
    inbound = {page.slug: 0 for page in pages}
    broken: list[dict[str, str]] = []
    missing_frontmatter: list[dict[str, object]] = []
    slug_issues: list[Page] = []
    misplaced: list[Page] = []
    stale_pages: list[Page] = []
    pages_without_ledger: list[Page] = []
    claim_rows = 0
    missing_sources = 0
    missing_confidence = 0
    missing_last_checked = 0
    weak_sources = 0

    required_root_files = ["WIKI_SCHEMA.md", "AGENTS.md", "CLAUDE.md", "wiki/index.md", "wiki/log.md"]
    missing_required = [path for path in required_root_files if not (root / path).exists()]
    for path in missing_required:
        warnings.append(warning("P1", path, eval_text(language, "missing_required_file"), "structure"))

    missing_sections = [section for section in WIKI_SECTIONS if not (root / "wiki" / section).exists()]
    for section in missing_sections:
        warnings.append(warning("P1", f"wiki/{section}/", eval_text(language, "missing_section"), "structure"))

    for page in pages:
        frontmatter = parse_frontmatter(page.text)
        missing = [key for key in ["title", "kind", "tags", "sources", "updated", "status"] if not frontmatter.get(key)]
        if missing:
            missing_frontmatter.append({"page": page, "missing": missing})
            warnings.append(
                warning("P2", page.rel, eval_text(language, "missing_frontmatter", fields=", ".join(missing)), "structure")
            )

        if not re.fullmatch(r"[a-z0-9\u4e00-\u9fa5]+(?:-[a-z0-9\u4e00-\u9fa5]+)*", page.slug):
            slug_issues.append(page)
            warnings.append(warning("P3", page.rel, eval_text(language, "unclean_slug"), "structure"))

        expected_section = frontmatter_section(frontmatter.get("kind", ""), page.section)
        if expected_section and expected_section != page.section:
            misplaced.append(page)
            warnings.append(
                warning(
                    "P3",
                    page.rel,
                    eval_text(language, "misplaced_page", expected=expected_section, actual=page.section),
                    "structure",
                )
            )

        if is_stale(page):
            stale_pages.append(page)
            warnings.append(
                warning(
                    "P2",
                    page.rel,
                    eval_text(language, "stale_page", updated=page.updated or eval_text(language, "unknown")),
                    "freshness",
                )
            )

        for link in page.links:
            if link not in known:
                broken.append({"from": page.slug, "to": link})
                warnings.append(warning("P1", page.rel, eval_text(language, "broken_wikilink", link=link), "links"))
            if link in inbound:
                inbound[link] += 1

        ledger_rows = extract_claim_ledger_rows(page.text)
        if ledger_rows:
            for row in ledger_rows:
                claim_rows += 1
                cells = row["cells"]
                source = cells[1].strip() if len(cells) > 1 else ""
                confidence = cells[2].strip() if len(cells) > 2 else ""
                last_checked = cells[3].strip() if len(cells) > 3 else ""
                if not source:
                    missing_sources += 1
                    warnings.append(
                        warning("P1", page.rel, eval_text(language, "claim_missing_source", line=row["line"]), "evidence")
                    )
                elif not is_traceable_source(source):
                    weak_sources += 1
                    warnings.append(
                        warning(
                            "P2",
                            page.rel,
                            eval_text(language, "claim_weak_source", line=row["line"], source=source),
                            "evidence",
                        )
                    )
                if not confidence:
                    missing_confidence += 1
                    warnings.append(
                        warning("P2", page.rel, eval_text(language, "claim_missing_confidence", line=row["line"]), "evidence")
                    )
                if not last_checked:
                    missing_last_checked += 1
                    warnings.append(
                        warning("P2", page.rel, eval_text(language, "claim_missing_last_checked", line=row["line"]), "evidence")
                    )
        elif page_should_have_claim_ledger(page):
            pages_without_ledger.append(page)
            warnings.append(warning("P2", page.rel, eval_text(language, "missing_claim_ledger"), "evidence"))

    orphan = [
        slug
        for slug, count in inbound.items()
        if count == 0 and slug not in {"overview", "synthesis"} and (len(pages) > 1 or slug != pages[0].slug)
    ]
    for slug in orphan:
        page = next((candidate for candidate in pages if candidate.slug == slug), None)
        warnings.append(warning("P3", page.rel if page else slug, eval_text(language, "orphan_page", slug=slug), "links"))

    overview = next((page for page in pages if page.slug == "overview"), None)
    synthesis = next((page for page in pages if page.slug == "synthesis"), None)
    coverage_warnings = 0
    if overview and is_stub_page(overview):
        coverage_warnings += 1
        warnings.append(warning("P2", overview.rel, eval_text(language, "overview_stub"), "coverage"))
    if synthesis and is_stub_page(synthesis):
        coverage_warnings += 1
        warnings.append(warning("P2", synthesis.rel, eval_text(language, "synthesis_stub"), "coverage"))
    raw_captures = list((root / "raw" / "captures").glob("*.md")) if (root / "raw" / "captures").exists() else []
    has_summary_pages = any(page.section == "summaries" for page in pages)
    if raw_captures and not has_summary_pages:
        coverage_warnings += 1
        warnings.append(warning("P2", "wiki/summaries/", eval_text(language, "captures_without_summaries"), "coverage"))

    large_pages = [page for page in pages if len(page.text) > 20000]
    for page in large_pages:
        warnings.append(warning("P3", page.rel, eval_text(language, "large_page"), "maintainability"))

    structure_score = clamp_score(100 - (len(missing_required) * 20 + len(missing_sections) * 15 + len(missing_frontmatter) * 8 + len(slug_issues) * 4 + len(misplaced) * 4))
    link_score = clamp_score(100 - (len(broken) * 20 + len(orphan) * 5))
    evidence_score = clamp_score(100 - (len(pages_without_ledger) * 12 + missing_sources * 15 + weak_sources * 8 + missing_confidence * 5 + missing_last_checked * 5))
    coverage_score = clamp_score(100 - coverage_warnings * 20)
    maintainability_score = clamp_score(100 - (len(stale_pages) * 10 + len(large_pages) * 5))
    overall = round(
        structure_score * 0.25
        + link_score * 0.15
        + evidence_score * 0.35
        + coverage_score * 0.15
        + maintainability_score * 0.10
    )

    return {
        "evaluated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": local_timezone_name(),
        "mode": "wiki",
        "subject": root,
        "language": language,
        "target": root,
        "pages": len(pages),
        "claim_rows": claim_rows,
        "raw_captures": len(raw_captures),
        "scores": {
            "overall": overall,
            "structure": structure_score,
            "links": link_score,
            "evidence": evidence_score,
            "coverage": coverage_score,
            "maintainability": maintainability_score,
        },
        "counts": {
            "warnings": len(warnings),
            "p1": count_severity(warnings, "P1"),
            "p2": count_severity(warnings, "P2"),
            "p3": count_severity(warnings, "P3"),
            "broken_links": len(broken),
            "orphan_pages": len(orphan),
            "missing_frontmatter": len(missing_frontmatter),
            "pages_without_claim_ledger": len(pages_without_ledger),
            "claim_rows_missing_source": missing_sources,
            "stale_pages": len(stale_pages),
        },
        "signals": wiki_quality_signals(
            missing_required,
            missing_sections,
            missing_frontmatter,
            slug_issues,
            misplaced,
            broken,
            orphan,
            pages_without_ledger,
            claim_rows,
            missing_sources,
            weak_sources,
            missing_confidence,
            missing_last_checked,
            overview,
            synthesis,
            raw_captures,
            has_summary_pages,
            large_pages,
            stale_pages,
            language,
        ),
        "warnings": warnings,
    }


def resolve_answer_file(root: Path, answer: str) -> Path:
    answer_path = Path(answer)
    candidates = [
        answer_path if answer_path.is_absolute() else root / answer_path,
        root / ".cwiki" / "answers" / answer_path.name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError(f"Answer file not found: {answer}")


def resolve_eval_all_answer_file(root: Path, answer: str | None, wiki_only: bool) -> Path | None:
    if wiki_only:
        return None
    if answer:
        return resolve_answer_file(root, answer)
    return latest_answer_file(root)


def latest_answer_file(root: Path) -> Path | None:
    answers_dir = root / ".cwiki" / "answers"
    if not answers_dir.is_dir():
        return None
    candidates = [path for path in answers_dir.glob("answer-*.md") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name)).resolve()


def answer_selection(root: Path, requested: str | None, selected: Path | None, wiki_only: bool) -> dict[str, object]:
    if wiki_only:
        mode = "wiki_only"
    elif requested:
        mode = "explicit"
    elif selected:
        mode = "latest"
    else:
        mode = "latest_not_found"
    return {
        "mode": mode,
        "requested": requested or "",
        "selected": display_path(selected, root) if selected else "",
    }


def build_answer_eval(root: Path, answer_file: Path, pages: list[Page]) -> dict[str, object]:
    text = answer_file.read_text(encoding="utf-8")
    language = detect_text_language(text, pages)
    known = {page.slug for page in pages}
    warnings: list[dict[str, str]] = []
    body = markdown_body(text)
    answer_body = extract_answer_body(body)
    frontmatter = parse_frontmatter(text)
    answer_content = strip_evaluation_scaffolding(answer_body)
    too_short_answer = len(answer_content) < 40 or (len(answer_content) < 120 and not re.search(r"[.!?。！？]", answer_content))
    if too_short_answer:
        warnings.append(warning("P1", display_path(answer_file, root), answer_eval_text(language, "answer_too_short"), "protocol"))
    if has_unclosed_wikilink(answer_body):
        warnings.append(warning("P1", display_path(answer_file, root), answer_eval_text(language, "unclosed_wikilink"), "protocol"))

    answer_links = wikilinks(answer_body)
    all_links = wikilinks(text)
    broken_links = [slug for slug in all_links if slug not in known]
    for slug in broken_links:
        warnings.append(warning("P1", display_path(answer_file, root), answer_eval_text(language, "broken_wikilink", slug=slug), "grounding"))

    if not answer_links:
        warnings.append(warning("P2", display_path(answer_file, root), answer_eval_text(language, "no_answer_citations"), "grounding"))

    prompt_paths = find_path_refs(answer_body, [".cwiki/prompts/"])
    for path in prompt_paths:
        warnings.append(warning("P2", display_path(answer_file, root), answer_eval_text(language, "prompt_as_source", path=path), "source_use"))

    source_refs = find_evidence_refs(answer_body)
    if not source_refs:
        warnings.append(warning("P2", display_path(answer_file, root), answer_eval_text(language, "no_source_refs"), "source_use"))

    unsupported = unsupported_factual_paragraphs(answer_body)
    for item in unsupported[:5]:
        warnings.append(
            warning(
                "P2",
                display_path(answer_file, root),
                answer_eval_text(language, "unsupported_paragraph", index=item["index"]),
                "source_use",
            )
        )

    relevant_pages = extract_relevant_page_slugs(text)
    explicitly_not_used = extract_not_used_page_slugs(text)
    used_relevant = sorted(set(relevant_pages).intersection(answer_links))
    missed_relevant = [
        slug
        for slug in relevant_pages
        if slug in known and slug not in set(answer_links) and slug not in explicitly_not_used
    ]
    if relevant_pages and not used_relevant:
        warnings.append(warning("P2", display_path(answer_file, root), answer_eval_text(language, "relevant_not_used"), "coverage"))
    elif missed_relevant:
        warnings.append(
            warning(
                "P3",
                display_path(answer_file, root),
                answer_eval_text(language, "some_relevant_not_used", slugs=", ".join(f"[[{slug}]]" for slug in missed_relevant[:5])),
                "coverage",
            )
        )

    sections = markdown_headings(body)
    missing_sections = [section for section in ["Question", "Answer"] if section not in sections]
    for section in missing_sections:
        warnings.append(warning("P2", display_path(answer_file, root), answer_eval_text(language, "missing_section", section=section), "protocol"))

    has_gap_signal = has_any_section(sections, ["Gaps", "Open Questions", "Uncertainty", "Limitations", "缺口", "开放问题", "不确定性", "限制"]) or re.search(
        r"\b(gap|gaps|unknown|uncertain|insufficient|not enough evidence)\b|缺口|未知|不确定|证据不足",
        body,
        flags=re.IGNORECASE,
    )
    if not has_gap_signal:
        warnings.append(warning("P3", display_path(answer_file, root), answer_eval_text(language, "missing_gaps"), "protocol"))

    urls = re.findall(r"https?://[^\s)`\]]+", answer_body)
    urls_without_access_date = bool(urls) and not re.search(r"\b(accessed|access date|last checked)\b|访问日期|访问时间|最后检查", body, flags=re.IGNORECASE)
    if urls_without_access_date:
        warnings.append(warning("P2", display_path(answer_file, root), answer_eval_text(language, "urls_without_access_date"), "source_use"))

    mentions_web = re.search(r"\bweb evidence\b|\bonline\b|\bbrowser\b|网络证据|联网|网页|浏览器", body, flags=re.IGNORECASE)
    web_without_sources = bool(mentions_web) and not has_any_section(sections, ["Sources", "Web evidence", "来源", "网络证据"])
    if web_without_sources:
        warnings.append(warning("P2", display_path(answer_file, root), answer_eval_text(language, "web_without_sources"), "protocol"))

    retrieval_result = retrieval_quality_eval(root, text, answer_links, warnings, language, answer_file)
    grounding_score = clamp_score(100 - (len(broken_links) * 25 + (0 if answer_links else 20)))
    source_score = clamp_score(100 - (len(unsupported) * 10 + len(prompt_paths) * 15 + (0 if source_refs else 15) + (10 if urls_without_access_date else 0)))
    coverage_score = clamp_score(100 - (len(missed_relevant) * 8 + (20 if relevant_pages and not used_relevant else 0)))
    protocol_score = clamp_score(
        100
        - (
            len(missing_sections) * 15
            + (0 if has_gap_signal else 10)
            + (20 if web_without_sources else 0)
            + (35 if too_short_answer else 0)
            + (30 if has_unclosed_wikilink(answer_body) else 0)
        )
    )
    risk = answer_risk(warnings, len(unsupported), len(broken_links))
    risk_penalty = {"low": 0, "medium": 2, "high": 5}[risk]
    overall = clamp_score(
        grounding_score * 0.35
        + source_score * 0.30
        + coverage_score * 0.15
        + protocol_score * 0.15
        + 100 * 0.05
        - risk_penalty
    )

    return {
        "evaluated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": local_timezone_name(),
        "mode": "answer",
        "subject": answer_file,
        "language": language,
        "target": root,
        "answer_file": answer_file,
        "question": extract_question_from_answer(text, frontmatter),
        "scores": {
            "overall": overall,
            "grounding": grounding_score,
            "source_use": source_score,
            "coverage": coverage_score,
            "protocol": protocol_score,
            "retrieval_quality": retrieval_result["score"],
        },
        "risk": risk,
        "counts": {
            "warnings": len(warnings),
            "p1": count_severity(warnings, "P1"),
            "p2": count_severity(warnings, "P2"),
            "p3": count_severity(warnings, "P3"),
            "wiki_citations": len(answer_links),
            "broken_wikilinks": len(broken_links),
            "source_refs": len(source_refs),
            "unsupported_paragraphs": len(unsupported),
            "relevant_pages": len(relevant_pages),
            "used_relevant_pages": len(used_relevant),
            "not_used_relevant_pages": len(explicitly_not_used),
            "answer_chars": len(answer_content),
            "retrieval_trace_available": bool(retrieval_result["available"]),
            "retrieval_direct_hits": len(retrieval_result["direct_hits"]),
            "retrieval_used_direct_hits": len(retrieval_result["used_direct_hits"]),
            "retrieval_graph_expanded": len(retrieval_result["graph_expanded"]),
            "retrieval_used_graph_expanded": len(retrieval_result["used_graph_expanded"]),
            "retrieval_path_evidence": retrieval_result["path_evidence_count"],
            "retrieval_fallback": bool(retrieval_result.get("fallback_reason")),
        },
        "signals": answer_quality_signals(
            answer_content,
            missing_sections,
            has_unclosed_wikilink(answer_body),
            answer_links,
            broken_links,
            source_refs,
            unsupported,
            relevant_pages,
            used_relevant,
            missed_relevant,
            explicitly_not_used,
            has_gap_signal,
            urls,
            urls_without_access_date,
            mentions_web,
            web_without_sources,
            risk,
            language,
            retrieval_result,
        ),
        "warnings": warnings,
        "retrieval": retrieval_result,
    }


def build_combined_eval(
    root: Path,
    wiki_result: dict[str, object],
    answer_result: dict[str, object] | None,
    answer_selection_result: dict[str, object],
) -> dict[str, object]:
    wiki_scores = wiki_result["scores"]
    answer_scores = answer_result["scores"] if answer_result else None
    wiki_counts = wiki_result["counts"]
    if answer_scores:
        overall = round(int(wiki_scores["overall"]) * 0.45 + int(answer_scores["overall"]) * 0.55)
    else:
        overall = int(wiki_scores["overall"])

    warnings = list(wiki_result["warnings"])
    if answer_result:
        warnings.extend(answer_result["warnings"])

    counts = {
        "warnings": len(warnings),
        "p1": count_severity(warnings, "P1"),
        "p2": count_severity(warnings, "P2"),
        "p3": count_severity(warnings, "P3"),
        "wiki_warnings": wiki_result["counts"]["warnings"],
        "answer_warnings": answer_result["counts"]["warnings"] if answer_result else 0,
        "has_answer": bool(answer_result),
        "wiki_broken_links": wiki_counts["broken_links"],
        "wiki_orphan_pages": wiki_counts["orphan_pages"],
        "wiki_missing_frontmatter": wiki_counts["missing_frontmatter"],
        "wiki_pages_without_claim_ledger": wiki_counts["pages_without_claim_ledger"],
        "wiki_claim_rows_missing_source": wiki_counts["claim_rows_missing_source"],
        "wiki_stale_pages": wiki_counts["stale_pages"],
    }

    return {
        "evaluated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": local_timezone_name(),
        "mode": "combined",
        "subject": root,
        "language": str((answer_result or wiki_result).get("language", "en")),
        "target": root,
        "answer_file": answer_result["answer_file"] if answer_result else None,
        "answer_selection": answer_selection_result,
        "question": answer_result["question"] if answer_result else "",
        "scores": {
            "overall": clamp_score(overall),
            "wiki_quality": wiki_scores["overall"],
            "answer_quality": answer_scores["overall"] if answer_scores else None,
        },
        "risk": answer_result.get("risk") if answer_result else None,
        "counts": counts,
        "signals": combined_quality_signals(wiki_result, answer_result),
        "warnings": warnings,
        "wiki": wiki_result,
        "answer": answer_result,
    }


def answer_risk(warnings: list[dict[str, str]], unsupported: int, broken_links: int) -> str:
    if count_severity(warnings, "P1") or broken_links or unsupported >= 3:
        return "high"
    if count_severity(warnings, "P2") or unsupported:
        return "medium"
    return "low"


def quality_signal(name: str, status: str, detail: str, score: int | None = None) -> dict[str, object]:
    signal: dict[str, object] = {"name": name, "status": status, "detail": detail}
    if score is not None:
        signal["score"] = clamp_score(score)
    return signal


def signal_status(fail: bool, warn: bool = False) -> str:
    if fail:
        return "fail"
    if warn:
        return "warn"
    return "pass"


def wiki_quality_signals(
    missing_required: list[str],
    missing_sections: list[str],
    missing_frontmatter: list[dict[str, object]],
    slug_issues: list[Page],
    misplaced: list[Page],
    broken: list[dict[str, str]],
    orphan: list[str],
    pages_without_ledger: list[Page],
    claim_rows: int,
    missing_sources: int,
    weak_sources: int,
    missing_confidence: int,
    missing_last_checked: int,
    overview: Page | None,
    synthesis: Page | None,
    raw_captures: list[Path],
    has_summary_pages: bool,
    large_pages: list[Page],
    stale_pages: list[Page],
    language: str,
) -> list[dict[str, object]]:
    has_summary_gap = bool(raw_captures) and not has_summary_pages
    overview_stub = overview is None or is_stub_page(overview)
    synthesis_stub = synthesis is None or is_stub_page(synthesis)
    overview_detail = "overview.md is missing or still reads like a stub" if overview_stub else "overview.md exists and has substantive orientation content"
    synthesis_detail = "synthesis.md is missing or still reads like a stub" if synthesis_stub else "synthesis.md exists and has substantive synthesis content"
    return [
        quality_signal("root_contract_files", signal_status(bool(missing_required)), f"Missing root files: {len(missing_required)}"),
        quality_signal("wiki_section_dirs", signal_status(bool(missing_sections)), f"Missing wiki sections: {len(missing_sections)}"),
        quality_signal("frontmatter_completeness", signal_status(False, bool(missing_frontmatter)), f"Pages with missing frontmatter fields: {len(missing_frontmatter)}"),
        quality_signal("slug_hygiene", signal_status(False, bool(slug_issues)), f"Pages with non-standard slugs: {len(slug_issues)}"),
        quality_signal("page_placement", signal_status(False, bool(misplaced)), f"Pages placed outside expected section: {len(misplaced)}"),
        quality_signal("link_integrity", signal_status(bool(broken)), f"Broken wikilinks: {len(broken)}"),
        quality_signal("graph_connectivity", signal_status(False, bool(orphan)), f"Orphan pages excluding overview/synthesis: {len(orphan)}"),
        quality_signal("claim_ledger_presence", signal_status(False, bool(pages_without_ledger)), f"Pages expected to have Claim Ledger but missing it: {len(pages_without_ledger)}"),
        quality_signal("claim_source_traceability", signal_status(bool(missing_sources), bool(weak_sources)), f"Claim rows: {claim_rows}; missing sources: {missing_sources}; weak sources: {weak_sources}"),
        quality_signal("claim_metadata_hygiene", signal_status(False, bool(missing_confidence or missing_last_checked)), f"Missing confidence: {missing_confidence}; missing last checked: {missing_last_checked}"),
        quality_signal("global_overview_page", signal_status(False, overview_stub), overview_detail),
        quality_signal("global_synthesis_page", signal_status(False, synthesis_stub), synthesis_detail),
        quality_signal("capture_to_summary_coverage", signal_status(False, has_summary_gap), f"Raw captures present: {len(raw_captures)}"),
        quality_signal("freshness", signal_status(False, bool(stale_pages)), f"Potentially stale pages: {len(stale_pages)}"),
        quality_signal("page_size_maintainability", signal_status(False, bool(large_pages)), f"Pages over maintainability threshold: {len(large_pages)}"),
    ]


def answer_quality_signals(
    answer_content: str,
    missing_sections: list[str],
    unclosed_wikilink: bool,
    answer_links: list[str],
    broken_links: list[str],
    source_refs: list[str],
    unsupported: list[dict[str, object]],
    relevant_pages: list[str],
    used_relevant: list[str],
    missed_relevant: list[str],
    explicitly_not_used: list[str],
    has_gap_signal: bool,
    urls: list[str],
    urls_without_access_date: bool,
    mentions_web: object,
    web_without_sources: bool,
    risk: str,
    language: str,
    retrieval_result: dict[str, object],
) -> list[dict[str, object]]:
    return [
        quality_signal("answer_body_completeness", signal_status(len(answer_content) < 40, len(answer_content) < 120), f"Answer body characters after scaffolding removal: {len(answer_content)}"),
        quality_signal("required_sections", signal_status(False, bool(missing_sections)), f"Missing required sections: {', '.join(missing_sections) if missing_sections else 'none'}"),
        quality_signal("wikilink_syntax", signal_status(unclosed_wikilink), "Unclosed wikilink detected" if unclosed_wikilink else "Wikilink syntax looks closed"),
        quality_signal("wiki_citation_grounding", signal_status(bool(broken_links), not answer_links), f"Wiki citations: {len(answer_links)}; broken: {len(broken_links)}"),
        quality_signal("source_path_or_url_use", signal_status(False, not source_refs), f"Source path/URL refs in answer body: {len(source_refs)}"),
        quality_signal("paragraph_support", signal_status(False, bool(unsupported)), f"Unsupported fact-like paragraphs: {len(unsupported)}"),
        quality_signal("relevant_page_usage", signal_status(False, bool(missed_relevant) or (bool(relevant_pages) and not used_relevant)), f"Relevant pages: {len(relevant_pages)}; used: {len(used_relevant)}; explicitly not used: {len(explicitly_not_used)}"),
        quality_signal("gaps_and_uncertainty", signal_status(False, not has_gap_signal), "Gaps/limitations signal present" if has_gap_signal else "No gaps/limitations signal found"),
        quality_signal("url_access_dates", signal_status(False, urls_without_access_date), f"URLs: {len(urls)}; missing access-date signal: {urls_without_access_date}"),
        quality_signal("web_evidence_protocol", signal_status(False, web_without_sources), "Web evidence mentioned without sources" if web_without_sources else "No web protocol issue detected"),
        quality_signal(
            "retrieval_quality",
            signal_status(int(retrieval_result.get("score", 0)) < 60, int(retrieval_result.get("score", 0)) < 85),
            f"Strategy: {retrieval_result.get('strategy', 'unknown')}; complexity: {retrieval_result.get('complexity', 'unknown')}; score: {retrieval_result.get('score', 0)}",
        ),
        quality_signal("risk_level", signal_status(risk == "high", risk == "medium"), f"Risk classified as {risk}"),
    ]


def combined_quality_signals(wiki_result: dict[str, object], answer_result: dict[str, object] | None) -> list[dict[str, object]]:
    signals = [
        quality_signal("wiki_component", signal_status(int(wiki_result["scores"]["overall"]) < 60, int(wiki_result["scores"]["overall"]) < 80), f"Wiki quality score: {wiki_result['scores']['overall']}"),
    ]
    if answer_result:
        signals.append(
            quality_signal("answer_component", signal_status(int(answer_result["scores"]["overall"]) < 60, int(answer_result["scores"]["overall"]) < 80), f"Answer quality score: {answer_result['scores']['overall']}")
        )
        signals.append(quality_signal("answer_risk", signal_status(answer_result.get("risk") == "high", answer_result.get("risk") == "medium"), f"Answer risk: {answer_result.get('risk')}"))
    else:
        signals.append(quality_signal("answer_component", "warn", "No answer file was included in combined evaluation"))
    return signals


def attach_llm_eval(
    root: Path,
    result: dict[str, object],
    enabled: bool,
    provider: str | None,
    model: str | None,
    api_key_env: str | None,
    base_url: str | None,
    max_output_tokens: int,
    agent_eval_file: str | None = None,
    agent_model: str | None = None,
) -> None:
    if agent_eval_file:
        result["llm_assisted"] = load_agent_platform_eval(root, agent_eval_file, agent_model)
        return
    if not enabled:
        result["llm_assisted"] = None
        return
    result["llm_assisted"] = run_llm_eval(root, result, provider, model, api_key_env, base_url, max_output_tokens)


def load_agent_platform_eval(root: Path, agent_eval_file: str, agent_model: str | None = None) -> dict[str, object]:
    path = resolve_agent_eval_file(root, agent_eval_file)
    payload = llm_eval_status("completed", "agent-platform", agent_model or "current-agent-model", "", "")
    payload["response"] = path.read_text(encoding="utf-8").strip()
    payload["prompt_version"] = "eval-agent-platform-v1"
    payload["source_file"] = display_path(path, root)
    payload["usage"] = {
        "status": "unavailable",
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "raw": {},
        "provider": "agent-platform",
        "model": agent_model or "current-agent-model",
    }
    payload["cost"] = estimate_llm_cost("agent-platform", agent_model or "current-agent-model", payload["usage"])
    return payload


def resolve_agent_eval_file(root: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise RuntimeError(f"Agent evaluation file not found: {value}")
    return candidate


def run_llm_eval(
    root: Path,
    result: dict[str, object],
    provider: str | None,
    model: str | None,
    api_key_env: str | None,
    base_url: str | None,
    max_output_tokens: int,
) -> dict[str, object]:
    load_local_env(root)
    resolved_provider = (provider or os.environ.get("CWIKI_EVAL_PROVIDER") or os.environ.get("CWIKI_PROVIDER") or "openai").lower()
    if resolved_provider not in {"openai", "glm"}:
        return llm_eval_status("failed", resolved_provider, model or "", api_key_env or "", f"Unsupported provider: {resolved_provider}")
    resolved_model = resolve_eval_model(resolved_provider, model)
    resolved_api_key_env = resolve_eval_api_key_env(resolved_provider, api_key_env)
    resolved_base_url = resolve_base_url(resolved_provider, base_url)
    if not os.environ.get(resolved_api_key_env):
        return llm_eval_status(
            "skipped",
            resolved_provider,
            resolved_model,
            resolved_api_key_env,
            f"Missing API key in {resolved_api_key_env}; deterministic evaluation is still complete.",
        )
    language = str(result.get("language", "en"))
    language_instruction = llm_eval_language_instruction(language)
    instructions = (
        "You are assisting with quality evaluation for an LLM Compound Wiki. "
        "This is an LLM-assisted evaluation, not the deterministic source of record. "
        "Do not remove, override, or hide deterministic warnings. "
        "Use the deterministic report and excerpts only. "
        f"{language_instruction} "
    )
    prompt = build_llm_eval_prompt(root, result)
    try:
        if resolved_provider == "openai":
            llm_response = call_openai_responses(os.environ[resolved_api_key_env], resolved_model, instructions, prompt, max_output_tokens)
        else:
            llm_response = call_openai_compatible_chat(
                api_key=os.environ[resolved_api_key_env],
                base_url=resolved_base_url,
                provider_name="GLM",
                model=resolved_model,
                instructions=instructions,
                prompt=prompt,
                max_output_tokens=max_output_tokens,
            )
    except RuntimeError as error:
        return llm_eval_status("failed", resolved_provider, resolved_model, resolved_api_key_env, str(error))
    payload = llm_eval_status("completed", resolved_provider, resolved_model, resolved_api_key_env, "")
    payload["response"] = llm_response.text
    payload["usage"] = llm_response.usage
    payload["cost"] = llm_response.cost
    payload["prompt_version"] = "eval-llm-v2"
    record_llm_usage(
        root,
        f"eval-{result.get('mode', 'wiki')}",
        resolved_provider,
        resolved_model,
        llm_response,
        artifact=str(result.get("answer_file") or result.get("target") or ""),
        question=str(result.get("question") or ""),
        metadata={"prompt_version": "eval-llm-v2"},
    )
    return payload


def llm_eval_language_instruction(language: str) -> str:
    if language == "zh-CN":
        return (
            "Respond entirely in Simplified Chinese. "
            "Return concise Markdown with exactly these sections: "
            "摘要, 额外风险, 优先修复, 置信度."
        )
    return "Respond in English. Return concise Markdown with sections: Summary, Additional Risks, Prioritized Fixes, Confidence."


def llm_eval_status(status: str, provider: str, model: str, api_key_env: str, reason: str) -> dict[str, object]:
    return {
        "status": status,
        "provider": provider,
        "model": model,
        "api_key_env": api_key_env,
        "evaluated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reason": reason,
    }


def resolve_eval_model(provider: str, model: str | None) -> str:
    if model:
        return model
    if os.environ.get("CWIKI_EVAL_MODEL"):
        return os.environ["CWIKI_EVAL_MODEL"]
    if provider == "glm":
        return os.environ.get("CWIKI_EVAL_GLM_MODEL") or resolve_model(provider, None)
    return os.environ.get("CWIKI_EVAL_OPENAI_MODEL") or resolve_model(provider, None)


def resolve_eval_api_key_env(provider: str, api_key_env: str | None) -> str:
    if api_key_env:
        return api_key_env
    if os.environ.get("CWIKI_EVAL_API_KEY_ENV"):
        return os.environ["CWIKI_EVAL_API_KEY_ENV"]
    return resolve_api_key_env(provider, None)


def build_llm_eval_prompt(root: Path, result: dict[str, object]) -> str:
    deterministic = {key: value for key, value in result.items() if key not in {"llm_assisted", "wiki", "answer"}}
    excerpts = "\n\n".join(eval_context_excerpts(root, result))
    language = str(result.get("language", "en"))
    language_label = "Simplified Chinese (zh-CN)" if language == "zh-CN" else "English"
    return f"""# LLM-Assisted Evaluation Request

Evaluation mode: {result.get('mode')}
Target: {display_path(Path(result.get('target', root)), root) if result.get('target') else root.as_posix()}
Required response language: {language_label}

## Deterministic Report JSON

```json
{json.dumps(jsonable(deterministic), ensure_ascii=False, indent=2)}
```

## Context Excerpts

{excerpts or '- No additional excerpts collected.'}

## Task

1. Review whether deterministic warnings point to the right practical risks.
2. Identify quality risks that deterministic checks may miss.
3. Prioritize fixes that would most improve future wiki maintenance and answer quality.
4. State confidence and limitations of this LLM-assisted evaluation.
5. Use the required response language. Do not switch languages unless source snippets must be quoted exactly.
"""


def eval_context_excerpts(root: Path, result: dict[str, object]) -> list[str]:
    excerpts: list[str] = []
    for rel in ["wiki/overview.md", "wiki/synthesis.md", "wiki/index.md"]:
        path = root / rel
        if path.is_file():
            excerpts.append(f"### {rel}\n\n{truncate_text(path.read_text(encoding='utf-8'), 2500)}")
    answer_file = result.get("answer_file")
    if answer_file:
        path = Path(answer_file)
        if path.is_file():
            excerpts.append(f"### {display_path(path, root)}\n\n{truncate_text(path.read_text(encoding='utf-8'), 5000)}")
    return excerpts


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n[truncated]"


def markdown_body(text: str) -> str:
    return re.sub(r"^---\n[\s\S]*?\n---\n?", "", text).strip()


def extract_markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^##+\s+{re.escape(heading)}\s*$", flags=re.MULTILINE | re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return ""
    next_heading = re.search(r"^##+\s+", text[match.end() :], flags=re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end].strip()


def extract_answer_body(text: str) -> str:
    match = re.search(r"^##+\s+Answer\s*$", text, flags=re.MULTILINE | re.IGNORECASE)
    if not match:
        return text
    stop = re.search(
        r"^##+\s+(Relevant Pages|Query Prompt|Sources|References)\s*$",
        text[match.end() :],
        flags=re.MULTILINE | re.IGNORECASE,
    )
    end = match.end() + stop.start() if stop else len(text)
    return text[match.end() : end].strip()


def strip_evaluation_scaffolding(text: str) -> str:
    cleaned = re.sub(r"^##+\s+(Evidence Used|Gaps|Relevant Pages|Query Prompt)\s*$[\s\S]*?(?=^##+\s+|\Z)", "", text, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r"^[-*]\s+\[\[[^\]]+\]\].*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"`[^`]+`", "", cleaned)
    cleaned = re.sub(r"\[\[[^\]]+\]\]", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def has_unclosed_wikilink(text: str) -> bool:
    return text.count("[[") != text.count("]]")


def markdown_headings(text: str) -> set[str]:
    return {match.group(1).strip() for match in re.finditer(r"^##+\s+(.+?)\s*$", text, flags=re.MULTILINE)}


def has_any_section(sections: set[str], names: list[str]) -> bool:
    normalized = {section.lower() for section in sections}
    return any(name.lower() in normalized for name in names)


def find_path_refs(text: str, prefixes: list[str]) -> list[str]:
    refs = re.findall(r"(?<![\w/.-])(?:\.?/)?(?:raw|wiki|\.cwiki)/(?:[^\s)`\]]+)", text)
    return sorted({ref for ref in refs if any(ref.startswith(prefix) or ref.startswith(f"./{prefix}") for prefix in prefixes)})


def find_evidence_refs(text: str) -> list[str]:
    refs = re.findall(r"https?://[^\s)`\]]+|(?<![\w/.-])(?:\.?/)?(?:raw|wiki|\.cwiki/web-research)/(?:[^\s)`\]]+)", text)
    return sorted(set(refs))


def unsupported_factual_paragraphs(text: str) -> list[dict[str, object]]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    unsupported: list[dict[str, object]] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        if paragraph.startswith("#") or paragraph.startswith("|") or paragraph.startswith("```"):
            continue
        if not looks_factual(paragraph):
            continue
        if find_evidence_refs(paragraph) or wikilinks(paragraph):
            continue
        unsupported.append({"index": index, "text": paragraph})
    return unsupported


def looks_factual(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) < 70:
        return False
    return bool(
        re.search(r"\b(is|are|was|were|has|have|shows|uses|supports|requires|includes|causes|improves|reduces|current|latest|recent)\b", compact, flags=re.IGNORECASE)
        or re.search(r"\d{2,}|20\d{2}|19\d{2}", compact)
        or re.search(r"是|为|包括|支持|需要|可以|通过|基于|导致|提升|降低|最新|当前|近期", compact)
    )


def extract_relevant_page_slugs(text: str) -> list[str]:
    section = extract_markdown_section(markdown_body(text), "Relevant Pages")
    if not section:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for slug in wikilinks(section):
        if slug not in seen:
            seen.add(slug)
            result.append(slug)
    return result


def extract_query_prompt_ref(text: str) -> str:
    section = extract_markdown_section(markdown_body(text), "Query Prompt")
    if not section:
        return ""
    refs = find_path_refs(section, [".cwiki/prompts/"])
    return refs[0] if refs else ""


def resolve_query_prompt_file(root: Path, answer_text: str) -> Path | None:
    ref = extract_query_prompt_ref(answer_text)
    if not ref:
        return None
    normalized = ref[2:] if ref.startswith("./") else ref
    candidate = (root / normalized).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def parse_retrieval_trace(prompt_text: str) -> dict[str, object]:
    frontmatter = parse_frontmatter(prompt_text)
    body = markdown_body(prompt_text)
    trace_section = extract_markdown_section(body, "Retrieval Trace")
    direct_section = extract_markdown_section(body, "Direct Hits")
    expanded_section = extract_markdown_section(body, "Graph-Expanded Pages")
    path_section = extract_markdown_section(body, "Path Evidence")
    final_section = extract_markdown_section(body, "Final Context Pages")
    path_lines = [line for line in path_section.splitlines() if "[[" in line and "None" not in line]
    graph_details = parse_graph_expanded_lines(expanded_section)
    path_evidence = [wikilinks(line) for line in path_lines]
    path_evidence = [path for path in path_evidence if len(path) >= 2]
    return {
        "available": bool(trace_section or frontmatter.get("retrieval_strategy")),
        "strategy": clean_quoted(frontmatter.get("retrieval_strategy", "")) or "unknown",
        "requested": clean_quoted(frontmatter.get("retrieval_requested", "")) or "unknown",
        "complexity": clean_quoted(frontmatter.get("retrieval_complexity", "")) or "unknown",
        "fallback_from": clean_quoted(frontmatter.get("retrieval_fallback_from", "")),
        "fallback_reason": clean_quoted(frontmatter.get("retrieval_fallback_reason", "")),
        "direct_hits": wikilinks(direct_section),
        "graph_expanded": list(dict.fromkeys(item["slug"] for item in graph_details)),
        "graph_expanded_details": graph_details,
        "path_evidence": path_evidence,
        "path_evidence_count": len(path_evidence),
        "final_pages": wikilinks(final_section),
    }


def parse_graph_expanded_lines(section: str) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for line in section.splitlines():
        if "[[" not in line or "None" in line:
            continue
        links = wikilinks(line)
        if not links:
            continue
        score_match = re.search(r"\]\]\s+\((\d+)\)", line)
        file_match = re.search(r"`([^`]+)`", line)
        reason = ""
        if "`" in line:
            tail = line.rsplit("`", 1)[-1].strip()
            reason = tail[1:].strip() if tail.startswith("-") else tail
        details.append(
            {
                "slug": links[0],
                "score": int(score_match.group(1)) if score_match else 0,
                "file": file_match.group(1) if file_match else "",
                "reason": reason,
                "line": line.strip(),
            }
        )
    return details


def add_graph_expanded_usage(details: object, answer_link_set: set[str]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    if not isinstance(details, list):
        return result
    for item in details:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug", ""))
        result.append({**item, "used_in_answer": slug in answer_link_set})
    return result


def retrieval_quality_eval(
    root: Path,
    answer_text: str,
    answer_links: list[str],
    warnings: list[dict[str, str]],
    language: str,
    answer_file: Path,
) -> dict[str, object]:
    prompt_ref = extract_query_prompt_ref(answer_text)
    prompt_file = resolve_query_prompt_file(root, answer_text)
    if not prompt_file:
        local_warnings = []
        score = 100
        if prompt_ref:
            warnings.append(warning("P3", display_path(answer_file, root), answer_eval_text(language, "retrieval_trace_missing"), "retrieval"))
            local_warnings = ["missing_trace"]
            score = 85
        return {
            "score": score,
            "prompt_file": prompt_ref,
            "available": False,
            "strategy": "unknown",
            "complexity": "unknown",
            "direct_hits": [],
            "used_direct_hits": [],
            "graph_expanded": [],
            "used_graph_expanded": [],
            "graph_expanded_details": [],
            "path_evidence_count": 0,
            "path_evidence": [],
            "fallback_from": "",
            "fallback_reason": "",
            "final_pages": [],
            "warnings": local_warnings,
        }

    prompt_text = prompt_file.read_text(encoding="utf-8")
    trace = parse_retrieval_trace(prompt_text)
    answer_link_set = set(answer_links)
    direct_hits = list(dict.fromkeys(str(slug) for slug in trace.get("direct_hits", [])))
    graph_expanded = list(dict.fromkeys(str(slug) for slug in trace.get("graph_expanded", [])))
    final_pages = list(dict.fromkeys(str(slug) for slug in trace.get("final_pages", [])))
    used_direct = sorted(answer_link_set.intersection(direct_hits))
    used_expanded = sorted(answer_link_set.intersection(graph_expanded))
    graph_expanded_details = add_graph_expanded_usage(trace.get("graph_expanded_details", []), answer_link_set)
    score = 100
    local_warnings: list[str] = []

    if not trace.get("available"):
        score -= 15
        local_warnings.append("missing_trace")
        warnings.append(warning("P3", display_path(prompt_file, root), answer_eval_text(language, "retrieval_trace_missing"), "retrieval"))
    if direct_hits and not used_direct:
        score -= 20
        local_warnings.append("direct_hits_not_used")
        warnings.append(warning("P2", display_path(answer_file, root), answer_eval_text(language, "retrieval_direct_not_used"), "retrieval"))
    unused_expanded = [slug for slug in graph_expanded if slug not in answer_link_set]
    if graph_expanded and len(unused_expanded) == len(graph_expanded):
        score -= 10
        local_warnings.append("graph_expansion_not_used")
    if trace.get("strategy") in {"path", "synthesis"} and int(trace.get("path_evidence_count", 0)) > 0:
        path_nodes_used = bool(answer_link_set.intersection(final_pages))
        if not path_nodes_used:
            score -= 15
            local_warnings.append("path_context_not_used")
    if trace.get("strategy") == "direct" and str(trace.get("complexity")) == "high":
        score -= 10
        local_warnings.append("complex_question_direct_only")

    return {
        "score": clamp_score(score),
        "prompt_file": display_path(prompt_file, root),
        "available": bool(trace.get("available")),
        "strategy": trace.get("strategy", "unknown"),
        "complexity": trace.get("complexity", "unknown"),
        "direct_hits": direct_hits,
        "used_direct_hits": used_direct,
        "graph_expanded": graph_expanded,
        "used_graph_expanded": used_expanded,
        "graph_expanded_details": graph_expanded_details,
        "path_evidence_count": int(trace.get("path_evidence_count", 0)),
        "path_evidence": trace.get("path_evidence", []),
        "fallback_from": trace.get("fallback_from", ""),
        "fallback_reason": trace.get("fallback_reason", ""),
        "final_pages": final_pages,
        "warnings": local_warnings,
    }


def extract_not_used_page_slugs(text: str) -> set[str]:
    result: set[str] = set()
    for line in text.splitlines():
        if re.search(r"\bnot used\b|未使用|没有使用|不使用", line, flags=re.IGNORECASE):
            result.update(wikilinks(line))
    return result


def extract_question_from_answer(text: str, frontmatter: dict[str, str]) -> str:
    if frontmatter.get("question"):
        return clean_quoted(frontmatter["question"])
    section = extract_markdown_section(markdown_body(text), "Question")
    return re.sub(r"\s+", " ", section).strip() if section else ""


def detect_text_language(text: str, pages: list[Page]) -> str:
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin = sum(1 for char in text if "a" <= char.lower() <= "z")
    if cjk >= 20 and cjk >= latin * 0.2:
        return "zh-CN"
    return detect_report_language(pages)


def detect_report_language(pages: list[Page]) -> str:
    content_pages = [
        page
        for page in pages
        if clean_quoted(parse_frontmatter(page.text).get("status", page.status)).lower() != "seed"
    ]
    sampled_pages = content_pages or pages
    sample = "\n".join(f"{page.title}\n{page.summary}\n{page.text}" for page in sampled_pages)[:200000]
    cjk = sum(1 for char in sample if "\u4e00" <= char <= "\u9fff")
    latin = sum(1 for char in sample if ("a" <= char.lower() <= "z"))
    return "zh-CN" if cjk >= 20 and cjk >= latin * 0.2 else "en"


def eval_text(language: str, key: str, **values: object) -> str:
    zh = {
        "missing_required_file": "缺少必要的 wiki 文件。",
        "missing_section": "缺少必要的 wiki 分区。",
        "missing_frontmatter": "缺少 frontmatter 字段：{fields}。",
        "unclean_slug": "文件名不是干净的小写 slug。",
        "misplaced_page": "页面 kind 指向 `{expected}/`，但文件位于 `{actual}/`。",
        "stale_page": "页面包含可能有时效性的表述；updated 为 {updated}。",
        "unknown": "未知",
        "broken_wikilink": "断开的 wikilink：[[{link}]]。",
        "claim_missing_source": "Claim Ledger 第 {line} 行缺少 source。",
        "claim_weak_source": "Claim Ledger 第 {line} 行的 source 不够清晰可追溯：{source}。",
        "claim_missing_confidence": "Claim Ledger 第 {line} 行缺少 confidence。",
        "claim_missing_last_checked": "Claim Ledger 第 {line} 行缺少 last checked 日期。",
        "missing_claim_ledger": "事实性 wiki 页面缺少 Claim Ledger。",
        "orphan_page": "孤立页面：[[{slug}]]。",
        "overview_stub": "overview 仍像是占位页，内容偏短。",
        "synthesis_stub": "synthesis 仍像是占位页，内容偏短。",
        "captures_without_summaries": "已经有 captured sources，但没有发现 summary 页面。",
        "large_page": "页面较大，agent 可能难以一次性完整审阅。",
    }
    en = {
        "missing_required_file": "Required wiki file is missing.",
        "missing_section": "Required wiki section is missing.",
        "missing_frontmatter": "Missing frontmatter fields: {fields}.",
        "unclean_slug": "Filename is not a clean lowercase slug.",
        "misplaced_page": "Page kind suggests `{expected}/` but file is under `{actual}/`.",
        "stale_page": "Time-sensitive language may be stale; updated {updated}.",
        "unknown": "unknown",
        "broken_wikilink": "Broken wikilink: [[{link}]].",
        "claim_missing_source": "Claim Ledger row {line} is missing a source.",
        "claim_weak_source": "Claim Ledger row {line} source is not clearly traceable: {source}.",
        "claim_missing_confidence": "Claim Ledger row {line} is missing confidence.",
        "claim_missing_last_checked": "Claim Ledger row {line} is missing last checked date.",
        "missing_claim_ledger": "Factual wiki page has no Claim Ledger.",
        "orphan_page": "Orphan page: [[{slug}]].",
        "overview_stub": "Overview appears to be a stub.",
        "synthesis_stub": "Synthesis appears to be a stub.",
        "captures_without_summaries": "Captured sources exist but no summary pages were found.",
        "large_page": "Page is large and may be difficult for agents to inspect in one pass.",
    }
    template = (zh if language == "zh-CN" else en)[key]
    return template.format(**values)


def answer_eval_text(language: str, key: str, **values: object) -> str:
    zh = {
        "broken_wikilink": "答案引用了不存在的 wiki 页面：[[{slug}]]。",
        "no_answer_citations": "答案正文没有使用本地 wiki 引用。",
        "prompt_as_source": "答案正文把工作 prompt 当作来源引用：{path}。",
        "no_source_refs": "答案正文没有引用 source path 或 URL。",
        "unsupported_paragraph": "第 {index} 个事实性段落附近缺少 wiki/source/URL 证据。",
        "relevant_not_used": "答案列出了 Relevant Pages，但正文没有实际引用这些页面。",
        "some_relevant_not_used": "部分 Relevant Pages 没有在正文中使用：{slugs}。",
        "missing_section": "答案缺少 `{section}` 章节。",
        "missing_gaps": "答案没有明确说明 gaps、限制或不确定性。",
        "urls_without_access_date": "答案包含 URL，但没有明显的访问日期或 last checked 信息。",
        "web_without_sources": "答案提到联网/网络证据，但缺少 Sources 或 Web evidence 章节。",
        "answer_too_short": "答案正文过短，可能是截断或只输出了评估脚手架。",
        "unclosed_wikilink": "答案包含未闭合的 wikilink，可能是生成被截断。",
        "retrieval_trace_missing": "没有找到本次问答的 Retrieval Trace，无法评估检索质量。",
        "retrieval_direct_not_used": "本次检索的直接命中页面没有在答案正文中使用。",
    }
    en = {
        "broken_wikilink": "Answer cites a missing wiki page: [[{slug}]].",
        "no_answer_citations": "Answer body does not use local wiki citations.",
        "prompt_as_source": "Answer body treats a working prompt as a source: {path}.",
        "no_source_refs": "Answer body does not cite source paths or URLs.",
        "unsupported_paragraph": "Fact-like paragraph {index} has no nearby wiki/source/URL evidence.",
        "relevant_not_used": "Answer lists Relevant Pages but does not cite them in the answer body.",
        "some_relevant_not_used": "Some Relevant Pages are not used in the answer body: {slugs}.",
        "missing_section": "Answer is missing a `{section}` section.",
        "missing_gaps": "Answer does not state gaps, limitations, or uncertainty.",
        "urls_without_access_date": "Answer includes URLs but no obvious access date or last checked information.",
        "web_without_sources": "Answer mentions web/online evidence but has no Sources or Web evidence section.",
        "answer_too_short": "Answer body is too short and may be truncated or only contain evaluation scaffolding.",
        "unclosed_wikilink": "Answer contains an unclosed wikilink and may be truncated.",
        "retrieval_trace_missing": "No Retrieval Trace was found for this answer, so retrieval quality cannot be evaluated.",
        "retrieval_direct_not_used": "The answer does not use any direct-hit pages from retrieval.",
    }
    template = (zh if language == "zh-CN" else en)[key]
    return template.format(**values)


def warning(severity: str, file: str, message: str, category: str) -> dict[str, str]:
    return {"severity": severity, "file": file, "message": message, "category": category}


def clamp_score(value: int | float) -> int:
    return max(0, min(100, round(value)))


def count_severity(warnings: list[dict[str, str]], severity: str) -> int:
    return sum(1 for item in warnings if item["severity"] == severity)


def highest_severity(warnings: list[dict[str, str]]) -> str:
    for severity in ["P1", "P2", "P3"]:
        if count_severity(warnings, severity):
            return severity
    return "-"


def local_timezone_name() -> str:
    if time.daylight and time.localtime().tm_isdst > 0:
        return time.tzname[1] or "local"
    return time.tzname[0] or "local"


def frontmatter_section(kind: str, fallback: str) -> str:
    normalized = clean_quoted(kind).lower()
    mapping = {
        "summary": "summaries",
        "summaries": "summaries",
        "entity": "entities",
        "entities": "entities",
        "concept": "concepts",
        "concepts": "concepts",
        "comparison": "comparisons",
        "comparisons": "comparisons",
    }
    return mapping.get(normalized, "" if fallback == "root" else fallback)


def extract_claim_ledger_rows(text: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if re.match(r"^##+\s+Claim Ledger\s*$", line.strip(), re.IGNORECASE)), None)
    if start is None:
        return []
    rows: list[dict[str, object]] = []
    for index in range(start + 1, len(lines)):
        line = lines[index].strip()
        if line.startswith("##"):
            break
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0].lower() == "claim" and cells[1].lower() == "source":
            continue
        if len(cells) >= 2 and any(cells):
            rows.append({"line": index + 1, "cells": cells})
    return rows


def is_traceable_source(source: str) -> bool:
    value = source.strip().strip("`")
    return bool(
        value.startswith("raw/")
        or value.startswith("./raw/")
        or value.startswith("wiki/")
        or value.startswith(".cwiki/web-research/")
        or value.startswith("./.cwiki/web-research/")
        or value.startswith("http://")
        or value.startswith("https://")
    )


def page_should_have_claim_ledger(page: Page) -> bool:
    frontmatter = parse_frontmatter(page.text)
    if clean_quoted(frontmatter.get("status", page.status)).lower() == "seed":
        return False
    if clean_quoted(frontmatter.get("sources", "")).strip() == "0":
        return False
    if page.slug == "overview":
        return False
    if page.section in {"summaries", "entities", "concepts", "comparisons"}:
        return len(page.text.strip()) > 250
    return page.slug == "synthesis" and len(page.text.strip()) > 250


def is_stub_page(page: Page) -> bool:
    body = re.sub(r"^---\n[\s\S]*?\n---\n?", "", page.text).strip()
    body = re.sub(r"^#\s+.+$", "", body, flags=re.MULTILINE).strip()
    return len(body) < 120 or "No summary yet" in body


def render_deterministic_note(result: dict[str, object], language: str) -> str:
    llm_status = str((result.get("llm_assisted") or {}).get("status", "")) if isinstance(result.get("llm_assisted"), dict) else ""
    has_llm = bool(llm_status and llm_status != "not_requested")
    if language == "zh-CN":
        if has_llm:
            return "- 本报告包含确定性评估和 LLM-assisted evaluation；确定性评估部分未使用 LLM。"
        return "- 本报告是确定性评估报告，未使用 LLM。"
    if has_llm:
        return "- This report includes deterministic evaluation and LLM-assisted evaluation; the deterministic section does not use an LLM."
    return "- This report is deterministic and does not use an LLM."


def render_wiki_eval_report(root: Path, result: dict[str, object]) -> str:
    scores = result["scores"]
    counts = result["counts"]
    warnings = result["warnings"]
    evaluated_at = result["evaluated_at"]
    date = str(evaluated_at).split(" ")[0]
    language = str(result.get("language", "en"))
    warning_lines = render_eval_warnings(warnings, language)
    signal_lines = render_eval_signals(result.get("signals", []), language)
    next_steps = render_eval_next_steps(warnings, language)
    llm_frontmatter = render_llm_frontmatter(result)
    llm_section = render_llm_assisted_section(result, language)
    deterministic_note = render_deterministic_note(result, language)
    if language == "zh-CN":
        return f"""---
title: Wiki 质量评估 - {evaluated_at}
tags: [evaluation, wiki-quality]
created: {evaluated_at}
evaluated_at: {evaluated_at}
evaluation_timezone: {result['timezone']}
updated: {date}
status: final
mode: wiki
{llm_frontmatter}
report_language: zh-CN
target: {root.as_posix()}
answer_file:
question:
source_file:
raw_capture:
ingest_prompt:
query_prompt:
web_research_file:
operation_log_entry:
overall: {scores['overall']}
---

# Wiki 质量评估 - {evaluated_at}

## 确定性评估

总体：{scores['overall']}/100
结构：{scores['structure']}/100
链接：{scores['links']}/100
证据：{scores['evidence']}/100
覆盖度：{scores['coverage']}/100
可维护性：{scores['maintainability']}/100

## 范围

- 目标：`{root.as_posix()}`
- 评估时间：{evaluated_at}
- 评估时区：{result['timezone']}
- 页面数：{result['pages']}
- 原始捕获数：{result['raw_captures']}
- Claim Ledger 行数：{result['claim_rows']}

## 计数

- 警告总数：{counts['warnings']}
- P1：{counts['p1']}
- P2：{counts['p2']}
- P3：{counts['p3']}
- 断链数：{counts['broken_links']}
- 孤立页面数：{counts['orphan_pages']}
- 缺少 frontmatter 的页面数：{counts['missing_frontmatter']}
- 缺少 Claim Ledger 的页面数：{counts['pages_without_claim_ledger']}
- 缺少 source 的 Claim 行数：{counts['claim_rows_missing_source']}
- 可能过期的页面数：{counts['stale_pages']}

## 警告

{warning_lines}

## 细分质量信号

{signal_lines}

## 建议下一步

{next_steps}

{llm_section}

## 说明

{deterministic_note}
- 它检查本地结构、链接、证据卫生、覆盖信号和可维护性信号。
- 它不会在未读取原始来源正文的情况下断言事实真伪。
"""
    return f"""---
title: Wiki Evaluation - {evaluated_at}
tags: [evaluation, wiki-quality]
created: {evaluated_at}
evaluated_at: {evaluated_at}
evaluation_timezone: {result['timezone']}
updated: {date}
status: final
mode: wiki
{llm_frontmatter}
report_language: en
target: {root.as_posix()}
answer_file:
question:
source_file:
raw_capture:
ingest_prompt:
query_prompt:
web_research_file:
operation_log_entry:
overall: {scores['overall']}
---

# Wiki Evaluation - {evaluated_at}

## Deterministic Evaluation

Overall: {scores['overall']}/100
Structure: {scores['structure']}/100
Links: {scores['links']}/100
Evidence: {scores['evidence']}/100
Coverage: {scores['coverage']}/100
Maintainability: {scores['maintainability']}/100

## Scope

- Target: `{root.as_posix()}`
- Evaluated at: {evaluated_at}
- Evaluation timezone: {result['timezone']}
- Pages: {result['pages']}
- Raw captures: {result['raw_captures']}
- Claim Ledger rows: {result['claim_rows']}

## Counts

- Warnings: {counts['warnings']}
- P1: {counts['p1']}
- P2: {counts['p2']}
- P3: {counts['p3']}
- Broken links: {counts['broken_links']}
- Orphan pages: {counts['orphan_pages']}
- Missing frontmatter pages: {counts['missing_frontmatter']}
- Pages without Claim Ledger: {counts['pages_without_claim_ledger']}
- Claim rows missing source: {counts['claim_rows_missing_source']}
- Stale pages: {counts['stale_pages']}

## Warnings

{warning_lines}

## Detailed Quality Signals

{signal_lines}

## Suggested Next Steps

{next_steps}

{llm_section}

## Notes

{deterministic_note}
- It checks local structure, links, evidence hygiene, coverage signals, and maintainability signals.
- It does not prove factual truth against original sources.
"""


def render_graph_expanded_eval_details(retrieval: object, language: str) -> str:
    if not isinstance(retrieval, dict):
        return "- 暂无图谱扩展页面。" if language == "zh-CN" else "- No graph-expanded pages."
    details = retrieval.get("graph_expanded_details", [])
    if not isinstance(details, list) or not details:
        return "- 暂无图谱扩展页面。" if language == "zh-CN" else "- No graph-expanded pages."
    lines: list[str] = []
    for item in details:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug", ""))
        file = str(item.get("file", ""))
        reason = str(item.get("reason", "")) or "-"
        score = item.get("score", 0)
        used = bool(item.get("used_in_answer"))
        if language == "zh-CN":
            used_text = "已在答案引用" if used else "未在答案引用"
        else:
            used_text = "used in answer" if used else "not cited in answer"
        file_text = f" `{file}`" if file else ""
        lines.append(f"- [[{slug}]] ({score}){file_text} - {reason} - {used_text}")
    return "\n".join(lines) if lines else ("- 暂无图谱扩展页面。" if language == "zh-CN" else "- No graph-expanded pages.")


def render_path_evidence_eval_details(retrieval: object, language: str) -> str:
    if not isinstance(retrieval, dict):
        return "- 暂无路径证据。" if language == "zh-CN" else "- No path evidence."
    paths = retrieval.get("path_evidence", [])
    if not isinstance(paths, list) or not paths:
        return "- 暂无路径证据。" if language == "zh-CN" else "- No path evidence."
    lines: list[str] = []
    for path in paths:
        if not isinstance(path, list) or len(path) < 2:
            continue
        lines.append("- " + " -> ".join(f"[[{slug}]]" for slug in path))
    return "\n".join(lines) if lines else ("- 暂无路径证据。" if language == "zh-CN" else "- No path evidence.")


def render_answer_eval_report(root: Path, result: dict[str, object]) -> str:
    scores = result["scores"]
    counts = result["counts"]
    warnings = result["warnings"]
    evaluated_at = result["evaluated_at"]
    date = str(evaluated_at).split(" ")[0]
    language = str(result.get("language", "en"))
    answer_file = Path(result["answer_file"])
    retrieval = result.get("retrieval", {})
    warning_lines = render_eval_warnings(warnings, language)
    signal_lines = render_eval_signals(result.get("signals", []), language)
    next_steps = render_answer_eval_next_steps(warnings, language)
    llm_frontmatter = render_llm_frontmatter(result)
    llm_section = render_llm_assisted_section(result, language)
    web_followup_section = render_web_followup_section(result, language)
    deterministic_note = render_deterministic_note(result, language)
    graph_details = render_graph_expanded_eval_details(retrieval, language)
    path_details = render_path_evidence_eval_details(retrieval, language)
    if language == "zh-CN":
        return f"""---
title: Answer 质量评估 - {evaluated_at}
tags: [evaluation, answer-quality]
created: {evaluated_at}
evaluated_at: {evaluated_at}
evaluation_timezone: {result['timezone']}
updated: {date}
status: final
mode: answer
{llm_frontmatter}
report_language: zh-CN
target: {root.as_posix()}
answer_file: {display_path(answer_file, root)}
question: {result['question']}
overall: {scores['overall']}
risk: {result['risk']}
---

# Answer 质量评估 - {evaluated_at}

## 确定性评估

总体：{scores['overall']}/100
Grounding：{scores['grounding']}/100
来源使用：{scores['source_use']}/100
覆盖度：{scores['coverage']}/100
协议遵守：{scores['protocol']}/100
检索质量：{scores.get('retrieval_quality', '-')}/100
风险：{risk_label(result['risk'], language)}

## 范围

- 目标 wiki：`{root.as_posix()}`
- 答案文件：`{display_path(answer_file, root)}`
- 问题：{result['question'] or '-'}
- 评估时间：{evaluated_at}
- 评估时区：{result['timezone']}

## 计数

- 警告总数：{counts['warnings']}
- P1：{counts['p1']}
- P2：{counts['p2']}
- P3：{counts['p3']}
- wiki 引用数：{counts['wiki_citations']}
- 断开的 wiki 引用数：{counts['broken_wikilinks']}
- source/URL 引用数：{counts['source_refs']}
- 缺少证据的事实性段落数：{counts['unsupported_paragraphs']}
- Relevant Pages 数：{counts['relevant_pages']}
- 已使用的 Relevant Pages 数：{counts['used_relevant_pages']}
- 明确说明未使用的 Relevant Pages 数：{counts['not_used_relevant_pages']}
- Retrieval Trace：{'yes' if counts.get('retrieval_trace_available') else 'no'}
- 检索策略：{retrieval.get('strategy', 'unknown')}
- 检索复杂度：{retrieval.get('complexity', 'unknown')}
- 直接命中使用数：{counts.get('retrieval_used_direct_hits', 0)}/{counts.get('retrieval_direct_hits', 0)}
- 图谱扩展使用数：{counts.get('retrieval_used_graph_expanded', 0)}/{counts.get('retrieval_graph_expanded', 0)}
- 路径证据数：{counts.get('retrieval_path_evidence', 0)}
- 检索回退：{retrieval.get('fallback_reason') or 'none'}
- 答案正文字符数：{counts['answer_chars']}

## 警告

{warning_lines}

## 细分质量信号

{signal_lines}

## 建议下一步

{next_steps}

## 检索质量

- Query Prompt：`{retrieval.get('prompt_file') or '-'}`
- Strategy used：{retrieval.get('strategy', 'unknown')}
- Complexity：{retrieval.get('complexity', 'unknown')}
- Direct hit usage：{len(retrieval.get('used_direct_hits', []))}/{len(retrieval.get('direct_hits', []))}
- Graph expansion usage：{len(retrieval.get('used_graph_expanded', []))}/{len(retrieval.get('graph_expanded', []))}
- Path evidence count：{retrieval.get('path_evidence_count', 0)}
- Fallback：{retrieval.get('fallback_reason') or 'none'}
- Retrieval warnings：{', '.join(retrieval.get('warnings', [])) if retrieval.get('warnings') else 'none'}

### Graph-Expanded Pages 明细

{graph_details}

### Path Evidence 明细

{path_details}

{llm_section}
{web_followup_section}

## 说明

{deterministic_note}
- 它检查 grounding、来源使用、上下文覆盖、协议结构和风险信号。
- 它不会在未读取原始来源正文的情况下断言答案事实真伪。
"""
    return f"""---
title: Answer Evaluation - {evaluated_at}
tags: [evaluation, answer-quality]
created: {evaluated_at}
evaluated_at: {evaluated_at}
evaluation_timezone: {result['timezone']}
updated: {date}
status: final
mode: answer
{llm_frontmatter}
report_language: en
target: {root.as_posix()}
answer_file: {display_path(answer_file, root)}
question: {result['question']}
overall: {scores['overall']}
risk: {result['risk']}
---

# Answer Evaluation - {evaluated_at}

## Deterministic Evaluation

Overall: {scores['overall']}/100
Grounding: {scores['grounding']}/100
Source Use: {scores['source_use']}/100
Coverage: {scores['coverage']}/100
Protocol: {scores['protocol']}/100
Retrieval Quality: {scores.get('retrieval_quality', '-')}/100
Risk: {result['risk']}

## Scope

- Target wiki: `{root.as_posix()}`
- Answer file: `{display_path(answer_file, root)}`
- Question: {result['question'] or '-'}
- Evaluated at: {evaluated_at}
- Evaluation timezone: {result['timezone']}

## Counts

- Warnings: {counts['warnings']}
- P1: {counts['p1']}
- P2: {counts['p2']}
- P3: {counts['p3']}
- Wiki citations: {counts['wiki_citations']}
- Broken wiki citations: {counts['broken_wikilinks']}
- Source/URL refs: {counts['source_refs']}
- Unsupported fact-like paragraphs: {counts['unsupported_paragraphs']}
- Relevant Pages: {counts['relevant_pages']}
- Used Relevant Pages: {counts['used_relevant_pages']}
- Explicitly Not Used Relevant Pages: {counts['not_used_relevant_pages']}
- Retrieval Trace: {'yes' if counts.get('retrieval_trace_available') else 'no'}
- Retrieval strategy: {retrieval.get('strategy', 'unknown')}
- Retrieval complexity: {retrieval.get('complexity', 'unknown')}
- Direct hit usage: {counts.get('retrieval_used_direct_hits', 0)}/{counts.get('retrieval_direct_hits', 0)}
- Graph expansion usage: {counts.get('retrieval_used_graph_expanded', 0)}/{counts.get('retrieval_graph_expanded', 0)}
- Path evidence count: {counts.get('retrieval_path_evidence', 0)}
- Retrieval fallback: {retrieval.get('fallback_reason') or 'none'}
- Answer body characters: {counts['answer_chars']}

## Warnings

{warning_lines}

## Detailed Quality Signals

{signal_lines}

## Suggested Next Steps

{next_steps}

## Retrieval Quality

- Query Prompt: `{retrieval.get('prompt_file') or '-'}`
- Strategy used: {retrieval.get('strategy', 'unknown')}
- Complexity: {retrieval.get('complexity', 'unknown')}
- Direct hit usage: {len(retrieval.get('used_direct_hits', []))}/{len(retrieval.get('direct_hits', []))}
- Graph expansion usage: {len(retrieval.get('used_graph_expanded', []))}/{len(retrieval.get('graph_expanded', []))}
- Path evidence count: {retrieval.get('path_evidence_count', 0)}
- Fallback: {retrieval.get('fallback_reason') or 'none'}
- Retrieval warnings: {', '.join(retrieval.get('warnings', [])) if retrieval.get('warnings') else 'none'}

### Graph-Expanded Pages Detail

{graph_details}

### Path Evidence Detail

{path_details}

{llm_section}
{web_followup_section}

## Notes

{deterministic_note}
- It checks grounding, source use, context coverage, protocol structure, and risk signals.
- It does not prove factual truth against original sources.
"""


def render_combined_eval_report(root: Path, result: dict[str, object]) -> str:
    scores = result["scores"]
    counts = result["counts"]
    warnings = result["warnings"]
    evaluated_at = result["evaluated_at"]
    date = str(evaluated_at).split(" ")[0]
    language = str(result.get("language", "en"))
    answer_file = result.get("answer_file")
    selection = result.get("answer_selection", {})
    selection_mode = selection.get("mode", "unknown") if isinstance(selection, dict) else "unknown"
    answer_file_display = display_path(Path(answer_file), root) if answer_file else ""
    answer_line = f"`{answer_file_display}`" if answer_file_display else "-"
    answer_score = scores["answer_quality"] if scores["answer_quality"] is not None else "-"
    risk = result.get("risk") or "-"
    warning_lines = render_eval_warnings(warnings, language)
    signal_lines = render_eval_signals(result.get("signals", []), language)
    next_steps = render_combined_eval_next_steps(warnings, language)
    llm_frontmatter = render_llm_frontmatter(result)
    llm_section = render_llm_assisted_section(result, language)
    deterministic_note = render_deterministic_note(result, language)

    if language == "zh-CN":
        return f"""---
title: 综合质量评估 - {evaluated_at}
tags: [evaluation, combined-quality]
created: {evaluated_at}
evaluated_at: {evaluated_at}
evaluation_timezone: {result['timezone']}
updated: {date}
status: final
mode: combined
{llm_frontmatter}
report_language: zh-CN
target: {root.as_posix()}
answer_file: {answer_file_display}
question: {result.get('question') or ''}
overall: {scores['overall']}
wiki_quality: {scores['wiki_quality']}
answer_quality: {answer_score}
risk: {risk}
---

# 综合质量评估 - {evaluated_at}

## 确定性评估

总体：{scores['overall']}/100
Wiki 质量：{scores['wiki_quality']}/100
问答质量：{answer_score}{'/100' if isinstance(answer_score, int) else ''}
风险：{risk_label(str(risk), language) if risk != '-' else '-'}

## 范围

- 目标 wiki：`{root.as_posix()}`
- 答案文件：{answer_line}
- 答案选择：{selection_mode}
- 问题：{result.get('question') or '-'}
- 评估时间：{evaluated_at}
- 评估时区：{result['timezone']}

## 计数

- 警告总数：{counts['warnings']}
- P1：{counts['p1']}
- P2：{counts['p2']}
- P3：{counts['p3']}
- Wiki 警告数：{counts['wiki_warnings']}
- Answer 警告数：{counts['answer_warnings']}

### Wiki 质量计数

- 断链数：{counts['wiki_broken_links']}
- 孤立页面数：{counts['wiki_orphan_pages']}
- 缺少 frontmatter 的页面数：{counts['wiki_missing_frontmatter']}
- 缺少 Claim Ledger 的页面数：{counts['wiki_pages_without_claim_ledger']}
- 缺少 source 的 Claim 行数：{counts['wiki_claim_rows_missing_source']}
- 可能过期的页面数：{counts['wiki_stale_pages']}

## 警告

{warning_lines}

## 细分质量信号

{signal_lines}

## 建议下一步

{next_steps}

{llm_section}

## 说明

{deterministic_note}
- `eval-all` 总是评估 wiki；默认会自动选择 `.cwiki/answers/` 下最新的 `answer-*.md`，也可以用 `--answer` 指定答案。
- 当使用 `--wiki-only` 或找不到答案文件时，综合分数等同于 wiki 质量分数，不会虚构问答质量分数。
"""

    return f"""---
title: Combined Evaluation - {evaluated_at}
tags: [evaluation, combined-quality]
created: {evaluated_at}
evaluated_at: {evaluated_at}
evaluation_timezone: {result['timezone']}
updated: {date}
status: final
mode: combined
{llm_frontmatter}
report_language: en
target: {root.as_posix()}
answer_file: {answer_file_display}
question: {result.get('question') or ''}
overall: {scores['overall']}
wiki_quality: {scores['wiki_quality']}
answer_quality: {answer_score}
risk: {risk}
---

# Combined Evaluation - {evaluated_at}

## Deterministic Evaluation

Overall: {scores['overall']}/100
Wiki Quality: {scores['wiki_quality']}/100
Answer Quality: {answer_score}{'/100' if isinstance(answer_score, int) else ''}
Risk: {risk}

## Scope

- Target wiki: `{root.as_posix()}`
- Answer file: {answer_line}
- Answer selection: {selection_mode}
- Question: {result.get('question') or '-'}
- Evaluated at: {evaluated_at}
- Evaluation timezone: {result['timezone']}

## Counts

- Warnings: {counts['warnings']}
- P1: {counts['p1']}
- P2: {counts['p2']}
- P3: {counts['p3']}
- Wiki warnings: {counts['wiki_warnings']}
- Answer warnings: {counts['answer_warnings']}

### Wiki Quality Counts

- Broken links: {counts['wiki_broken_links']}
- Orphan pages: {counts['wiki_orphan_pages']}
- Missing frontmatter pages: {counts['wiki_missing_frontmatter']}
- Pages without Claim Ledger: {counts['wiki_pages_without_claim_ledger']}
- Claim rows missing source: {counts['wiki_claim_rows_missing_source']}
- Stale pages: {counts['wiki_stale_pages']}

## Warnings

{warning_lines}

## Detailed Quality Signals

{signal_lines}

## Suggested Next Steps

{next_steps}

{llm_section}

## Notes

{deterministic_note}
- `eval-all` always evaluates wiki quality; by default it selects the latest `.cwiki/answers/answer-*.md`, and `--answer` can pin a specific answer.
- When `--wiki-only` is used or no answer file exists, the combined score equals the wiki quality score and no answer quality score is invented.
"""


def render_combined_eval_next_steps(warnings: list[dict[str, str]], language: str) -> str:
    if not warnings:
        return "- 暂无需要立即修复的问题。" if language == "zh-CN" else "- No immediate fixes suggested."
    wiki_categories = {"structure", "links", "evidence", "freshness", "maintainability"}
    answer_categories = {"grounding", "source_use", "protocol"}
    categories = {item["category"] for item in warnings}
    if language == "zh-CN":
        steps: list[str] = []
        if categories.intersection(wiki_categories):
            steps.append("- 先修复 wiki 结构、链接、证据或可维护性 warning，避免后续答案继续继承问题。")
        if "coverage" in categories:
            steps.append("- 检查 overview、synthesis、Relevant Pages 与答案正文是否覆盖了关键上下文。")
        if categories.intersection(answer_categories):
            steps.append("- 重新生成或修订答案，补齐 wiki 引用、source path/URL、Gaps 和协议化章节。")
        return "\n".join(steps[:5])
    steps = []
    if categories.intersection(wiki_categories):
        steps.append("- Fix wiki structure, link, evidence, or maintainability warnings before relying on downstream answers.")
    if "coverage" in categories:
        steps.append("- Review overview, synthesis, Relevant Pages, and answer body coverage.")
    if categories.intersection(answer_categories):
        steps.append("- Regenerate or revise the answer with wiki citations, source paths/URLs, Gaps, and required sections.")
    return "\n".join(steps[:5])


def render_eval_signals(signals: list[dict[str, object]], language: str) -> str:
    if not signals:
        return "- 暂无细分信号。" if language == "zh-CN" else "- No detailed signals."
    lines = []
    for item in signals:
        score = f" `{item['score']}/100`" if "score" in item else ""
        lines.append(f"- [{str(item.get('status', 'unknown')).upper()}]{score} `{item.get('name')}`: {item.get('detail')}")
    return "\n".join(lines)


def render_llm_frontmatter(result: dict[str, object]) -> str:
    llm = result.get("llm_assisted")
    if not isinstance(llm, dict):
        return (
            "llm_assisted: false\n"
            "llm_provider:\n"
            "llm_model:\n"
            "llm_status:\n"
            f"{llm_usage_frontmatter(None, None)}"
        )
    return (
        "llm_assisted: true\n"
        f"llm_provider: {llm.get('provider', '')}\n"
        f"llm_model: {llm.get('model', '')}\n"
        f"llm_status: {llm.get('status', '')}\n"
        f"{llm_usage_frontmatter(llm.get('usage') if isinstance(llm.get('usage'), dict) else None, llm.get('cost') if isinstance(llm.get('cost'), dict) else None)}"
    )


def render_llm_assisted_section(result: dict[str, object], language: str) -> str:
    llm = result.get("llm_assisted")
    if not isinstance(llm, dict):
        return ""
    heading = "## LLM-Assisted Evaluation" if language != "zh-CN" else "## LLM-Assisted Evaluation（大模型辅助评估）"
    provider = llm.get("provider", "-")
    model = llm.get("model", "-")
    status = llm.get("status", "-")
    reason = llm.get("reason", "")
    response = str(llm.get("response", "")).strip()
    if not response:
        response = f"- {reason}" if reason else "- No LLM response was produced."
    source_file = str(llm.get("source_file", "") or "")
    source_line = f"- Source file: `{source_file}`\n" if source_file else ""
    usage = llm.get("usage") if isinstance(llm.get("usage"), dict) else None
    cost = llm.get("cost") if isinstance(llm.get("cost"), dict) else None
    usage_lines = llm_usage_bullets(usage, cost) if usage or cost else "- Usage: unavailable"
    return f"""
{heading}

- Provider: `{provider}`
- Model: `{model}`
- Status: `{status}`
- Evaluated at: {llm.get('evaluated_at', '-')}
{source_line}
{usage_lines}

{response}
"""


def render_web_followup_section(result: dict[str, object], language: str) -> str:
    followup = result.get("web_followup")
    if not isinstance(followup, dict):
        return ""
    heading = "## Web Gap Follow-up" if language != "zh-CN" else "## 联网补证任务"
    status = followup.get("status", "-")
    reason = followup.get("reason", "-")
    categories = followup.get("categories") if isinstance(followup.get("categories"), list) else []
    excerpts = followup.get("matched_excerpts") if isinstance(followup.get("matched_excerpts"), list) else []
    category_lines = "\n".join(f"- {item.get('reason')}" for item in categories if isinstance(item, dict)) or "- None"
    excerpt_lines = "\n".join(f"- {item}" for item in excerpts if item) or "- None"
    if language == "zh-CN":
        artifact_lines = (
            f"- Web query prompt：`{followup.get('web_query_prompt', '-')}`\n"
            f"- Web research workspace：`{followup.get('web_research_file', '-')}`\n"
            f"- Evidence fusion prompt：`{followup.get('fusion_prompt', '-')}`\n"
            f"- Follow-up report：`{followup.get('followup_report', '-')}`"
            if followup.get("triggered")
            else "- 未生成联网补证产物。"
        )
        return f"""
{heading}

- 状态：`{status}`
- 原因：{reason}
- 证据权重：wiki `{followup.get('wiki_weight', '-')}`，web `{followup.get('web_weight', '-')}`，web mode `{followup.get('web_mode', '-')}`
- 最大 web 来源数：{followup.get('max_web_sources', '-')}

### 触发类别

{category_lines}

### 命中的缺口片段

{excerpt_lines}

### 产物

{artifact_lines}
"""
    artifact_lines = (
        f"- Web query prompt: `{followup.get('web_query_prompt', '-')}`\n"
        f"- Web research workspace: `{followup.get('web_research_file', '-')}`\n"
        f"- Evidence fusion prompt: `{followup.get('fusion_prompt', '-')}`\n"
        f"- Follow-up report: `{followup.get('followup_report', '-')}`"
        if followup.get("triggered")
        else "- No web follow-up artifacts were created."
    )
    return f"""
{heading}

- Status: `{status}`
- Reason: {reason}
- Evidence weights: wiki `{followup.get('wiki_weight', '-')}`, web `{followup.get('web_weight', '-')}`, web mode `{followup.get('web_mode', '-')}`
- Max web sources: {followup.get('max_web_sources', '-')}

### Trigger Categories

{category_lines}

### Matched Gap Excerpts

{excerpt_lines}

### Artifacts

{artifact_lines}
"""


def render_eval_json(result: dict[str, object]) -> str:
    deterministic = {key: value for key, value in result.items() if key != "llm_assisted"}
    payload = {
        "deterministic": jsonable(deterministic),
        "llm_assisted": jsonable(result.get("llm_assisted")),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def jsonable(value: object) -> object:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    return value


def iso_now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def env_fragment(value: str) -> str:
    fragment = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    return fragment or "UNKNOWN"


def llm_usage_from_response(provider: str, model: str, data: dict[str, object]) -> dict[str, object]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return {
            "status": "unavailable",
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "raw": {},
            "provider": provider,
            "model": model,
        }
    input_tokens = first_int(usage, ("input_tokens", "prompt_tokens"))
    output_tokens = first_int(usage, ("output_tokens", "completion_tokens"))
    total_tokens = first_int(usage, ("total_tokens",))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return {
        "status": "reported" if any(value is not None for value in (input_tokens, output_tokens, total_tokens)) else "unavailable",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "raw": jsonable(usage),
        "provider": provider,
        "model": model,
    }


def first_int(data: dict[str, object], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = int_or_none(data.get(key))
        if value is not None:
            return value
    return None


def usage_price_env_names(provider: str, model: str, direction: str) -> list[str]:
    provider_key = env_fragment(provider)
    model_key = env_fragment(model)
    return [
        f"CWIKI_COST_{provider_key}_{model_key}_{direction}_PER_1M",
        f"CWIKI_COST_{provider_key}_{direction}_PER_1M",
        f"CWIKI_COST_{direction}_PER_1M",
    ]


def usage_currency_env_names(provider: str, model: str) -> list[str]:
    provider_key = env_fragment(provider)
    model_key = env_fragment(model)
    return [
        f"CWIKI_COST_{provider_key}_{model_key}_CURRENCY",
        f"CWIKI_COST_{provider_key}_CURRENCY",
        "CWIKI_COST_CURRENCY",
    ]


def first_float_env(names: list[str]) -> tuple[float | None, str]:
    for name in names:
        value = os.environ.get(name)
        if value is None or value.strip() == "":
            continue
        try:
            return float(value), name
        except ValueError as error:
            raise RuntimeError(f"Invalid cost rate for {name}: {value}") from error
    return None, ""


def first_str_env(names: list[str], default: str) -> tuple[str, str]:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip(), name
    return default, ""


def estimate_llm_cost(provider: str, model: str, usage: dict[str, object]) -> dict[str, object]:
    input_tokens = int_or_none(usage.get("input_tokens"))
    output_tokens = int_or_none(usage.get("output_tokens"))
    total_tokens = int_or_none(usage.get("total_tokens"))
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return {
            "status": "unavailable",
            "currency": first_str_env(usage_currency_env_names(provider, model), "USD")[0],
            "input_cost": None,
            "output_cost": None,
            "total_cost": None,
            "rates": {},
        }

    currency, currency_env = first_str_env(usage_currency_env_names(provider, model), "USD")
    input_rate, input_rate_env = first_float_env(usage_price_env_names(provider, model, "INPUT"))
    output_rate, output_rate_env = first_float_env(usage_price_env_names(provider, model, "OUTPUT"))
    total_rate, total_rate_env = first_float_env(usage_price_env_names(provider, model, "TOTAL"))

    rates: dict[str, object] = {}
    if input_rate is not None:
        rates["input_per_1m"] = input_rate
        rates["input_env"] = input_rate_env
    if output_rate is not None:
        rates["output_per_1m"] = output_rate
        rates["output_env"] = output_rate_env
    if total_rate is not None:
        rates["total_per_1m"] = total_rate
        rates["total_env"] = total_rate_env
    if currency_env:
        rates["currency_env"] = currency_env

    input_cost = round(input_tokens * input_rate / 1_000_000, 8) if input_tokens is not None and input_rate is not None else None
    output_cost = round(output_tokens * output_rate / 1_000_000, 8) if output_tokens is not None and output_rate is not None else None
    total_cost = None
    if input_cost is not None or output_cost is not None:
        total_cost = round((input_cost or 0.0) + (output_cost or 0.0), 8)
    elif total_tokens is not None and total_rate is not None:
        total_cost = round(total_tokens * total_rate / 1_000_000, 8)

    if total_cost is None:
        status = "unconfigured"
    elif (
        (input_tokens is None or input_rate is not None)
        and (output_tokens is None or output_rate is not None)
        and (input_tokens is not None or output_tokens is not None or total_rate is not None)
    ):
        status = "estimated"
    else:
        status = "partial"
    return {
        "status": status,
        "currency": currency,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "rates": rates,
    }


def usage_dir(root: Path) -> Path:
    return root / ".cwiki" / "usage"


def usage_ledger_file(root: Path) -> Path:
    return usage_dir(root) / "llm-usage.jsonl"


def append_usage_record(root: Path, record: dict[str, object]) -> None:
    path = usage_ledger_file(root)
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(jsonable(record), ensure_ascii=False, sort_keys=True) + "\n")


def usage_record_id(operation: str, provider: str, model: str, question: str, artifact: str) -> str:
    seed = f"{iso_now()}|{operation}|{provider}|{model}|{question}|{artifact}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return f"{timestamp()}-{slugify(operation) or 'llm'}-{digest}"


def record_llm_usage(
    root: Path,
    operation: str,
    provider: str,
    model: str,
    response: LLMResponse,
    artifact: str = "",
    question: str = "",
    prompt_file: str = "",
    status: str = "completed",
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    artifact_display = normalize_usage_path(root, artifact)
    prompt_display = normalize_usage_path(root, prompt_file)
    record = {
        "id": usage_record_id(operation, provider, model, question, artifact_display or prompt_display),
        "recorded_at": iso_now(),
        "operation": operation,
        "provider": provider,
        "model": model,
        "status": status,
        "artifact": artifact_display,
        "question": question,
        "prompt_file": prompt_display,
        "usage": response.usage,
        "cost": response.cost,
        "metadata": metadata or {},
    }
    append_usage_record(root, record)
    return record


def normalize_usage_path(root: Path, value: str | Path) -> str:
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return display_path(path, root)


def token_display(value: object) -> str:
    number = int_or_none(value)
    return str(number) if number is not None else "unknown"


def cost_display(cost: dict[str, object]) -> str:
    total = cost.get("total_cost")
    if isinstance(total, (int, float)):
        currency = str(cost.get("currency") or "USD")
        return f"{total:.6f} {currency}"
    return "unknown"


def llm_usage_line(usage: dict[str, object], cost: dict[str, object]) -> str:
    cost_total = cost.get("total_cost")
    cost_text = "unknown"
    if isinstance(cost_total, (int, float)):
        cost_text = f"{cost_total:.6f} {cost.get('currency') or 'USD'}"
    return (
        "LLM usage: "
        f"input={token_display(usage.get('input_tokens'))} "
        f"output={token_display(usage.get('output_tokens'))} "
        f"total={token_display(usage.get('total_tokens'))} "
        f"cost={cost_text} "
        f"({cost.get('status', 'unknown')})"
    )


def llm_usage_frontmatter(usage: dict[str, object] | None, cost: dict[str, object] | None) -> str:
    usage = usage or {}
    cost = cost or {}
    total_cost = cost.get("total_cost")
    total_cost_value = f"{float(total_cost):.8f}" if isinstance(total_cost, (int, float)) else ""
    return (
        f"llm_input_tokens: {frontmatter_scalar(usage.get('input_tokens'))}\n"
        f"llm_output_tokens: {frontmatter_scalar(usage.get('output_tokens'))}\n"
        f"llm_total_tokens: {frontmatter_scalar(usage.get('total_tokens'))}\n"
        f"llm_cost_status: {cost.get('status', '')}\n"
        f"llm_estimated_cost: {total_cost_value}\n"
        f"llm_cost_currency: {cost.get('currency', '')}"
    )


def frontmatter_scalar(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def llm_usage_bullets(usage: dict[str, object] | None, cost: dict[str, object] | None) -> str:
    usage = usage or {}
    cost = cost or {}
    total_cost = cost.get("total_cost")
    if isinstance(total_cost, (int, float)):
        cost_value = f"{total_cost:.6f} {cost.get('currency') or 'USD'}"
    else:
        cost_value = "unknown"
    return (
        f"- Input tokens: {token_display(usage.get('input_tokens'))}\n"
        f"- Output tokens: {token_display(usage.get('output_tokens'))}\n"
        f"- Total tokens: {token_display(usage.get('total_tokens'))}\n"
        f"- Cost status: {cost.get('status', 'unknown')}\n"
        f"- Estimated cost: {cost_value}"
    )


def read_usage_records(root: Path) -> list[dict[str, object]]:
    path = usage_ledger_file(root)
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def parse_usage_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as error:
        raise RuntimeError(f"Invalid date/time filter: {value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def record_time(record: dict[str, object]) -> dt.datetime | None:
    value = record.get("recorded_at")
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def filter_usage_records(
    records: list[dict[str, object]],
    operation: str | None = None,
    artifact: str | None = None,
    question: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, object]]:
    since_time = parse_usage_time(since)
    until_time = parse_usage_time(until)
    filtered: list[dict[str, object]] = []
    for record in records:
        if operation and str(record.get("operation", "")) != operation:
            continue
        if artifact and artifact not in str(record.get("artifact", "")) and artifact not in str(record.get("prompt_file", "")):
            continue
        if question and question not in str(record.get("question", "")):
            continue
        if provider and str(record.get("provider", "")) != provider:
            continue
        if model and str(record.get("model", "")) != model:
            continue
        seen_at = record_time(record)
        if since_time and seen_at and seen_at < since_time:
            continue
        if until_time and seen_at and seen_at > until_time:
            continue
        filtered.append(record)
    return filtered


def usage_summary(records: list[dict[str, object]]) -> dict[str, object]:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    unknown_token_records = 0
    costs_by_currency: dict[str, float] = {}
    by_operation: dict[str, dict[str, object]] = {}
    for record in records:
        usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
        cost = record.get("cost") if isinstance(record.get("cost"), dict) else {}
        in_tokens = int_or_none(usage.get("input_tokens")) if isinstance(usage, dict) else None
        out_tokens = int_or_none(usage.get("output_tokens")) if isinstance(usage, dict) else None
        total = int_or_none(usage.get("total_tokens")) if isinstance(usage, dict) else None
        if in_tokens is None and out_tokens is None and total is None:
            unknown_token_records += 1
        input_tokens += in_tokens or 0
        output_tokens += out_tokens or 0
        total_tokens += total if total is not None else (in_tokens or 0) + (out_tokens or 0)
        currency = str(cost.get("currency") or "USD") if isinstance(cost, dict) else "USD"
        total_cost = cost.get("total_cost") if isinstance(cost, dict) else None
        if isinstance(total_cost, (int, float)):
            costs_by_currency[currency] = round(costs_by_currency.get(currency, 0.0) + float(total_cost), 8)
        operation = str(record.get("operation") or "unknown")
        bucket = by_operation.setdefault(
            operation,
            {"records": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "costs_by_currency": {}},
        )
        bucket["records"] = int(bucket["records"]) + 1
        bucket["input_tokens"] = int(bucket["input_tokens"]) + (in_tokens or 0)
        bucket["output_tokens"] = int(bucket["output_tokens"]) + (out_tokens or 0)
        bucket["total_tokens"] = int(bucket["total_tokens"]) + (total if total is not None else (in_tokens or 0) + (out_tokens or 0))
        if isinstance(total_cost, (int, float)):
            operation_costs = bucket["costs_by_currency"]
            if isinstance(operation_costs, dict):
                operation_costs[currency] = round(float(operation_costs.get(currency, 0.0)) + float(total_cost), 8)
    return {
        "records": len(records),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "unknown_token_records": unknown_token_records,
        "costs_by_currency": costs_by_currency,
        "by_operation": by_operation,
    }


def render_costs(costs_by_currency: dict[str, float]) -> str:
    if not costs_by_currency:
        return "unknown"
    return ", ".join(f"{amount:.6f} {currency}" for currency, amount in sorted(costs_by_currency.items()))


def usage_records_table(records: list[dict[str, object]]) -> str:
    if not records:
        return "- No usage records matched."
    lines = ["| Time | Operation | Provider | Model | Tokens | Cost | Artifact |", "|---|---|---|---|---:|---:|---|"]
    for record in records:
        usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
        cost = record.get("cost") if isinstance(record.get("cost"), dict) else {}
        tokens = token_display(usage.get("total_tokens")) if isinstance(usage, dict) else "unknown"
        cost_text = "unknown"
        if isinstance(cost, dict) and isinstance(cost.get("total_cost"), (int, float)):
            cost_text = f"{float(cost['total_cost']):.6f} {cost.get('currency') or 'USD'}"
        artifact = str(record.get("artifact") or record.get("prompt_file") or "")
        if len(artifact) > 80:
            artifact = artifact[:77] + "..."
        lines.append(
            "| "
            + " | ".join(
                [
                    str(record.get("recorded_at", "")),
                    str(record.get("operation", "")),
                    str(record.get("provider", "")),
                    str(record.get("model", "")),
                    tokens,
                    cost_text,
                    artifact or "-",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def render_usage_report(records: list[dict[str, object]], filters: dict[str, object], json_output: bool = False) -> str:
    summary = usage_summary(records)
    payload = {
        "generated_at": iso_now(),
        "filters": {key: value for key, value in filters.items() if value not in (None, "")},
        "summary": summary,
        "records": records,
    }
    if json_output:
        return json.dumps(jsonable(payload), ensure_ascii=False, indent=2)
    filter_lines = "\n".join(f"- {key}: `{value}`" for key, value in payload["filters"].items()) or "- none"
    by_operation = summary.get("by_operation", {})
    if isinstance(by_operation, dict) and by_operation:
        operation_lines = ["| Operation | Records | Input | Output | Total | Cost |", "|---|---:|---:|---:|---:|---:|"]
        for operation, item in sorted(by_operation.items()):
            costs = item.get("costs_by_currency") if isinstance(item, dict) else {}
            operation_lines.append(
                f"| {operation} | {item.get('records', 0)} | {item.get('input_tokens', 0)} | "
                f"{item.get('output_tokens', 0)} | {item.get('total_tokens', 0)} | "
                f"{render_costs(costs if isinstance(costs, dict) else {})} |"
            )
        operation_table = "\n".join(operation_lines)
    else:
        operation_table = "- No usage records."
    return f"""# LLM Usage Cost Report

Generated at: {payload['generated_at']}

## Filters

{filter_lines}

## Summary

- Records: {summary['records']}
- Input tokens: {summary['input_tokens']}
- Output tokens: {summary['output_tokens']}
- Total tokens: {summary['total_tokens']}
- Records with unknown tokens: {summary['unknown_token_records']}
- Estimated cost: {render_costs(summary['costs_by_currency'] if isinstance(summary['costs_by_currency'], dict) else {})}

## By Operation

{operation_table}

## Records

{usage_records_table(records)}
"""


def usage_report_wiki(
    target: str,
    operation: str | None,
    artifact: str | None,
    question: str | None,
    provider: str | None,
    model: str | None,
    since: str | None,
    until: str | None,
    json_output: bool,
) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    load_local_env(root)
    filters = {
        "operation": operation,
        "artifact": artifact,
        "question": question,
        "provider": provider,
        "model": model,
        "since": since,
        "until": until,
    }
    records = filter_usage_records(read_usage_records(root), operation, artifact, question, provider, model, since, until)
    print(render_usage_report(records, filters, json_output))


def manual_usage_log_wiki(
    target: str,
    operation: str,
    provider: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    estimated_cost: float | None,
    currency: str,
    artifact: str | None,
    question: str | None,
    status: str,
    metadata_json: str | None,
) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    load_local_env(root)
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    usage = {
        "status": "reported" if any(value is not None for value in (input_tokens, output_tokens, total_tokens)) else "unavailable",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "raw": {},
        "provider": provider,
        "model": model,
    }
    cost = estimate_llm_cost(provider, model, usage)
    if estimated_cost is not None:
        cost = {
            "status": "provided",
            "currency": currency,
            "input_cost": None,
            "output_cost": None,
            "total_cost": estimated_cost,
            "rates": {},
        }
    metadata: dict[str, object] = {"recorded_by": "usage-log"}
    if metadata_json:
        try:
            extra = json.loads(metadata_json)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid --metadata-json: {error}") from error
        if not isinstance(extra, dict):
            raise RuntimeError("--metadata-json must decode to an object.")
        metadata.update(extra)
    record = record_llm_usage(
        root,
        operation,
        provider,
        model,
        LLMResponse("", usage, cost),
        artifact or "",
        question or "",
        "",
        status,
        metadata,
    )
    print(f"Recorded usage: {record['id']}")
    print(llm_usage_line(usage, cost))


def render_eval_warnings(warnings: list[dict[str, str]], language: str) -> str:
    if not warnings:
        return "- 暂无警告。" if language == "zh-CN" else "- No warnings."
    return "\n".join(
        f"- [{item['severity']}] `{item['file']}` ({eval_category_label(item['category'], language)}): {item['message']}"
        for item in warnings
    )


def render_eval_next_steps(warnings: list[dict[str, str]], language: str) -> str:
    if not warnings:
        return "- 暂无需要立刻修复的问题。" if language == "zh-CN" else "- No immediate fixes suggested."
    steps: list[str] = []
    categories = {item["category"] for item in warnings}
    if language == "zh-CN":
        if "evidence" in categories:
            steps.append("- 修复缺少来源或来源不够清晰的 Claim Ledger 行。")
        if "links" in categories:
            steps.append("- 修复断开的 wikilink，并检查孤立页面。")
        if "structure" in categories:
            steps.append("- 修复结构类 warning，例如缺失文件、frontmatter、slug 或页面分区问题。")
        if "coverage" in categories:
            steps.append("- 扩写 overview、synthesis，或为 captured sources 补充 summary 页面。")
        if "freshness" in categories:
            steps.append("- 在用于回答当前问题前复查可能过期的页面。")
        if "maintainability" in categories:
            steps.append("- 拆分或总结过大的页面，方便后续 agent 审阅。")
        return "\n".join(steps[:5])
    if "evidence" in categories:
        steps.append("- Fix Claim Ledger rows with missing or weak source metadata.")
    if "links" in categories:
        steps.append("- Fix broken wikilinks and review orphan pages.")
    if "structure" in categories:
        steps.append("- Fix structure warnings such as missing files, frontmatter, slugs, or page placement.")
    if "coverage" in categories:
        steps.append("- Expand overview, synthesis, or summary pages for captured sources.")
    if "freshness" in categories:
        steps.append("- Review stale pages before relying on them for current questions.")
    if "maintainability" in categories:
        steps.append("- Split or summarize pages that are too large for easy agent review.")
    return "\n".join(steps[:5])


def render_answer_eval_next_steps(warnings: list[dict[str, str]], language: str) -> str:
    if not warnings:
        return "- 暂无需要立刻修复的问题。" if language == "zh-CN" else "- No immediate fixes suggested."
    categories = {item["category"] for item in warnings}
    steps: list[str] = []
    if language == "zh-CN":
        if "grounding" in categories:
            steps.append("- 给答案正文补充真实存在的 wiki 页面引用，例如 `[[slug]]`。")
        if "source_use" in categories:
            steps.append("- 在事实性段落附近补充 source path、Claim Ledger 来源或精确 URL。")
        if "coverage" in categories:
            steps.append("- 回到 Relevant Pages，确保答案正文使用了应使用的上下文。")
        if "protocol" in categories:
            steps.append("- 补齐答案结构，尤其是 Question、Answer、Gaps/限制、Sources 等章节。")
        return "\n".join(steps[:5])
    if "grounding" in categories:
        steps.append("- Add valid wiki citations such as `[[slug]]` in the answer body.")
    if "source_use" in categories:
        steps.append("- Add source paths, Claim Ledger sources, or exact URLs near factual paragraphs.")
    if "coverage" in categories:
        steps.append("- Revisit Relevant Pages and cite the context actually used by the answer.")
    if "protocol" in categories:
        steps.append("- Complete answer structure, especially Question, Answer, Gaps/limitations, and Sources sections.")
    return "\n".join(steps[:5])


def risk_label(risk: str, language: str) -> str:
    if language != "zh-CN":
        return risk
    return {"low": "低", "medium": "中", "high": "高"}.get(risk, risk)


def eval_category_label(category: str, language: str) -> str:
    if language != "zh-CN":
        return category
    return {
        "structure": "结构",
        "links": "链接",
        "evidence": "证据",
        "coverage": "覆盖度",
        "freshness": "时效性",
        "maintainability": "可维护性",
        "grounding": "grounding",
        "source_use": "来源使用",
        "protocol": "协议",
    }.get(category, category)


def default_eval_report_path(root: Path, prefix: str, extension: str = "md") -> Path:
    return root / ".cwiki" / "eval" / f"{prefix}-{timestamp()}.{extension}"


def display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def update_eval_index(root: Path, report_file: Path, result: dict[str, object]) -> None:
    eval_dir = root / ".cwiki" / "eval"
    ensure_dir(eval_dir)
    index_file = eval_dir / "index.md"
    if not index_file.exists():
        index_file.write_text(
            "# Evaluation Index\n\n| Evaluated At | Mode | Subject | Report | Overall | Highest Severity |\n|---|---|---|---|---:|---|\n",
            encoding="utf-8",
        )
    rel_report = report_file.relative_to(eval_dir).as_posix() if report_file.is_relative_to(eval_dir) else report_file.as_posix()
    scores = result["scores"]
    severity = highest_severity(result["warnings"])
    mode = str(result.get("mode", "wiki"))
    subject = Path(result.get("subject", result["target"])).as_posix()
    row = f"| {result['evaluated_at']} | {mode} | `{subject}` | `{rel_report}` | {scores['overall']} | {severity} |\n"
    with index_file.open("a", encoding="utf-8") as handle:
        handle.write(row)


def parse_tags(value: str) -> list[str]:
    stripped = (value or "").strip()
    if not stripped:
        return []
    if stripped.startswith("[") and stripped.endswith("]"):
        stripped = stripped[1:-1]
    tags = []
    for item in stripped.split(","):
        tag = clean_quoted(item.strip())
        if tag:
            tags.append(tag)
    return tags


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(clean_quoted(value or ""))
    except ValueError:
        return default


def extract_claim_sources(page: Page) -> list[str]:
    lines = page.text.splitlines()
    in_ledger = False
    sources: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_ledger = stripped.lower() in {"## claim ledger", "## 声明台账", "## 事实台账"}
            continue
        if not in_ledger or not stripped.startswith("|") or stripped.startswith("|---"):
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() in {"claim", "声明"}:
            continue
        source = cells[1].strip()
        if not source or source in {"-", "source", "来源"}:
            continue
        if source not in seen:
            seen.add(source)
            sources.append(source)
    return sources


def build_wiki_graph(root: Path) -> dict[str, object]:
    pages = collect_pages(root)
    pages_by_slug = {page.slug: page for page in pages}
    inbound: dict[str, int] = {page.slug: 0 for page in pages}
    outbound: dict[str, int] = {page.slug: 0 for page in pages}
    edges: list[dict[str, object]] = []

    for page in pages:
        link_counts: dict[str, int] = {}
        for target in page.links:
            if target == page.slug:
                continue
            link_counts[target] = link_counts.get(target, 0) + 1
        for target, mentions in sorted(link_counts.items()):
            target_exists = target in pages_by_slug
            outbound[page.slug] += 1
            if target_exists:
                inbound[target] += 1
            edges.append(
                {
                    "source": page.slug,
                    "target": target,
                    "type": "WIKILINK",
                    "source_file": page.rel,
                    "target_exists": target_exists,
                    "confidence": "high" if target_exists else "broken",
                    "evidence": f"[[{target}]]",
                    "mentions": mentions,
                }
            )

    nodes = []
    for page in pages:
        frontmatter = parse_frontmatter(page.text)
        claim_sources = extract_claim_sources(page)
        nodes.append(
            {
                "id": page.slug,
                "title": page.title,
                "kind": page.kind,
                "section": page.section,
                "file": page.rel,
                "tags": parse_tags(page.tags),
                "updated": clean_quoted(page.updated),
                "status": clean_quoted(page.status),
                "summary": page.summary,
                "source_count": parse_int(frontmatter.get("sources", ""), len(claim_sources)),
                "claim_sources": claim_sources,
                "in_degree": inbound[page.slug],
                "out_degree": outbound[page.slug],
                "degree": inbound[page.slug] + outbound[page.slug],
            }
        )

    broken_edges = [edge for edge in edges if not edge["target_exists"]]
    isolated = [node["id"] for node in nodes if node["degree"] == 0]
    no_inbound = [node["id"] for node in nodes if node["in_degree"] == 0 and node["id"] not in {"overview", "synthesis"}]
    cross_section_edges = [
        edge
        for edge in edges
        if edge["target_exists"]
        and pages_by_slug[str(edge["source"])].section != pages_by_slug[str(edge["target"])].section
    ]

    return {
        "schema_version": "0.1",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "target": root.as_posix(),
        "nodes": sorted(nodes, key=lambda node: str(node["id"])),
        "edges": sorted(edges, key=lambda edge: (str(edge["source"]), str(edge["target"]))),
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "broken_edge_count": len(broken_edges),
            "isolated_node_count": len(isolated),
            "no_inbound_count": len(no_inbound),
            "cross_section_edge_count": len(cross_section_edges),
        },
    }


def graph_dir(root: Path) -> Path:
    return root / ".cwiki" / "graph"


def write_graph_json(root: Path, graph: dict[str, object]) -> Path:
    output_dir = graph_dir(root)
    ensure_dir(output_dir)
    output_file = output_dir / "graph.json"
    output_file.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_file


def graph_nodes_by_id(graph: dict[str, object]) -> dict[str, dict[str, object]]:
    nodes = graph.get("nodes", [])
    return {str(node["id"]): node for node in nodes if isinstance(node, dict) and "id" in node}


def graph_language(graph: dict[str, object]) -> str:
    nodes = graph.get("nodes", [])
    sample = "\n".join(str(node.get("title", "")) + "\n" + str(node.get("summary", "")) for node in nodes if isinstance(node, dict))
    return "zh" if contains_chinese(sample) else "en"


def render_graph_report(graph: dict[str, object]) -> str:
    language = graph_language(graph)
    nodes = graph_nodes_by_id(graph)
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    stats = graph.get("stats", {})
    top_nodes = sorted(nodes.values(), key=lambda node: (-int(node.get("degree", 0)), str(node.get("id", ""))))[:10]
    broken_edges = [edge for edge in edges if not edge.get("target_exists")]
    isolated = [node for node in nodes.values() if int(node.get("degree", 0)) == 0]
    cross_section_edges = [
        edge
        for edge in edges
        if edge.get("target_exists")
        and nodes[str(edge["source"])]["section"] != nodes[str(edge["target"])]["section"]
    ][:20]

    top_rows = "\n".join(
        f"| [[{node['id']}]] | {escape_cell(str(node.get('title', '')))} | {node.get('kind', '-')} | "
        f"{node.get('in_degree', 0)} | {node.get('out_degree', 0)} | {node.get('degree', 0)} |"
        for node in top_nodes
    ) or "| - | - | - | - | - | - |"
    broken_rows = "\n".join(
        f"- [[{edge['source']}]] -> [[{edge['target']}]] (`{edge['source_file']}`)"
        for edge in broken_edges[:30]
    ) or "- None"
    isolated_rows = "\n".join(f"- [[{node['id']}]] `{node.get('file', '')}`" for node in isolated[:30]) or "- None"
    cross_rows = "\n".join(
        f"- [[{edge['source']}]] ({nodes[str(edge['source'])]['section']}) -> "
        f"[[{edge['target']}]] ({nodes[str(edge['target'])]['section']})"
        for edge in cross_section_edges
    ) or "- None"

    if language == "zh":
        return f"""---
title: Wiki 图谱报告
tags: [graph, report]
updated: {today()}
status: generated
---

# Wiki 图谱报告

## 概览

- 节点数：{stats.get('node_count', 0)}
- 边数：{stats.get('edge_count', 0)}
- 断链数：{stats.get('broken_edge_count', 0)}
- 孤立节点数：{stats.get('isolated_node_count', 0)}
- 跨分区连接数：{stats.get('cross_section_edge_count', 0)}
- 生成时间：{graph.get('generated_at', '-')}

## 中心页面

| Page | Title | Kind | In | Out | Degree |
|---|---|---|---:|---:|---:|
{top_rows}

## 断链

{broken_rows}

## 孤立页面

{isolated_rows}

## 跨分区连接

{cross_rows}

## 建议问题

- 哪些中心页面应该更新 `overview.md` 或 `synthesis.md`？
- 哪些孤立页面需要补充 `[[wikilink]]`？
- 哪些断链应该创建新页面或修正 slug？
- 哪些跨分区连接代表了值得沉淀的综合主题？
"""

    return f"""---
title: Wiki Graph Report
tags: [graph, report]
updated: {today()}
status: generated
---

# Wiki Graph Report

## Overview

- Nodes: {stats.get('node_count', 0)}
- Edges: {stats.get('edge_count', 0)}
- Broken edges: {stats.get('broken_edge_count', 0)}
- Isolated nodes: {stats.get('isolated_node_count', 0)}
- Cross-section edges: {stats.get('cross_section_edge_count', 0)}
- Generated at: {graph.get('generated_at', '-')}

## Central Pages

| Page | Title | Kind | In | Out | Degree |
|---|---|---|---:|---:|---:|
{top_rows}

## Broken Links

{broken_rows}

## Isolated Pages

{isolated_rows}

## Cross-Section Edges

{cross_rows}

## Suggested Questions

- Which central pages should update `overview.md` or `synthesis.md`?
- Which isolated pages need more `[[wikilinks]]`?
- Which broken links should become new pages or corrected slugs?
- Which cross-section links reveal useful synthesis topics?
"""


def graph_wiki(target: str) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    graph = build_wiki_graph(root)
    output_file = write_graph_json(root, graph)
    stats = graph["stats"]
    print(f"Created graph: {output_file.relative_to(root).as_posix()}")
    print(
        f"Nodes: {stats['node_count']} | Edges: {stats['edge_count']} | "
        f"Broken: {stats['broken_edge_count']} | Isolated: {stats['isolated_node_count']}"
    )


def graph_report_wiki(target: str) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    graph = build_wiki_graph(root)
    graph_file = write_graph_json(root, graph)
    report_file = graph_dir(root) / "graph.md"
    report_file.write_text(render_graph_report(graph), encoding="utf-8")
    print(f"Created graph: {graph_file.relative_to(root).as_posix()}")
    print(f"Created graph report: {report_file.relative_to(root).as_posix()}")


def resolve_graph_slug(value: str, nodes: dict[str, dict[str, object]]) -> str:
    if value in nodes:
        return value
    slug = slugify(value)
    if slug in nodes:
        return slug
    lowered = value.lower()
    for node_id, node in nodes.items():
        if str(node.get("title", "")).lower() == lowered:
            return node_id
    raise RuntimeError(f"Unknown graph node: {value}")


def graph_adjacency(graph: dict[str, object]) -> dict[str, set[str]]:
    nodes = graph_nodes_by_id(graph)
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict) or not edge.get("target_exists"):
            continue
        source = str(edge["source"])
        target = str(edge["target"])
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
    return adjacency


def shortest_graph_path(graph: dict[str, object], start: str, goal: str) -> list[str]:
    adjacency = graph_adjacency(graph)
    if start == goal:
        return [start]
    queue: list[list[str]] = [[start]]
    seen = {start}
    for path in queue:
        current = path[-1]
        for neighbor in sorted(adjacency.get(current, set())):
            if neighbor in seen:
                continue
            next_path = [*path, neighbor]
            if neighbor == goal:
                return next_path
            seen.add(neighbor)
            queue.append(next_path)
    return []


def path_wiki(target: str, source: str, target_slug: str) -> int:
    root = Path(target).resolve()
    assert_wiki(root)
    graph = build_wiki_graph(root)
    nodes = graph_nodes_by_id(graph)
    start = resolve_graph_slug(source, nodes)
    goal = resolve_graph_slug(target_slug, nodes)
    path = shortest_graph_path(graph, start, goal)
    if not path:
        print(f"No graph path found between [[{start}]] and [[{goal}]].")
        return 1
    print(" -> ".join(f"[[{slug}]]" for slug in path))
    return 0


def explain_wiki_node(target: str, slug_value: str) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    graph = build_wiki_graph(root)
    nodes = graph_nodes_by_id(graph)
    slug = resolve_graph_slug(slug_value, nodes)
    node = nodes[slug]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    outgoing = [str(edge["target"]) for edge in edges if edge.get("source") == slug]
    incoming = [str(edge["source"]) for edge in edges if edge.get("target") == slug and edge.get("target_exists")]

    print(f"# [[{slug}]] — {node.get('title', slug)}")
    print(f"- File: `{node.get('file', '-')}`")
    print(f"- Kind: `{node.get('kind', '-')}`")
    print(f"- Section: `{node.get('section', '-')}`")
    print(f"- Updated: {node.get('updated') or '-'}")
    print(f"- Degree: {node.get('degree', 0)} (in {node.get('in_degree', 0)}, out {node.get('out_degree', 0)})")
    print(f"- Summary: {node.get('summary', '-')}")
    print("\n## Outgoing Links")
    print("\n".join(f"- [[{item}]]" for item in outgoing) or "- None")
    print("\n## Incoming Links")
    print("\n".join(f"- [[{item}]]" for item in incoming) or "- None")
    print("\n## Claim Sources")
    claim_sources = node.get("claim_sources", [])
    print("\n".join(f"- `{source}`" for source in claim_sources) if claim_sources else "- None")


def search_wiki(target: str, query: str) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    hits = find_hits(collect_pages(root), query, limit=20)

    if not hits:
        print(f'No matches for "{query}".')
        return
    for page, count in hits:
        print(f"- [[{page.slug}]] ({count}) {page.rel}")
        print(f"  {page.summary}")


def find_hits(pages: list[Page], query: str, limit: int, include_relation_boost: bool = True) -> list[tuple[Page, int]]:
    terms = expand_terms(query_terms(query))
    if not terms:
        terms = [term for term in re.split(r"[\s，。？！,.?;:：；、]+", query.lower().strip()) if term]
    if not terms:
        return []
    query_vector = text_vector(" ".join(terms) + "\n" + query)
    direct_scores: dict[str, int] = {}
    raw_scores: dict[str, float] = {}
    pages_by_slug = {page.slug: page for page in pages}

    for page in pages:
        haystack = f"{page.title}\n{page.summary}\n{page.tags}\n{page.text}".lower()
        title_slug = f"{page.title} {page.slug}".lower()
        keyword_score = sum(haystack.count(term) for term in terms)
        keyword_score += sum(title_slug.count(term) * 4 for term in terms)
        if query.lower() in haystack:
            keyword_score += 3
        direct_scores[page.slug] = keyword_score

        vector_score = cosine_similarity(query_vector, text_vector(haystack))
        if keyword_score > 0 or vector_score >= 0.18:
            raw_scores[page.slug] = keyword_score + (vector_score * 12)

    if include_relation_boost:
        for page in pages:
            if direct_scores.get(page.slug, 0) <= 0:
                continue
            relation_boost = max(1.0, min(4.0, direct_scores[page.slug] / 4))
            for linked_slug in page.links:
                if linked_slug in pages_by_slug:
                    raw_scores[linked_slug] = raw_scores.get(linked_slug, 0.0) + relation_boost
            for backlink in pages:
                if page.slug in backlink.links:
                    raw_scores[backlink.slug] = raw_scores.get(backlink.slug, 0.0) + relation_boost

    hits = [(pages_by_slug[slug], max(1, round(score))) for slug, score in raw_scores.items() if score > 0]
    hits.sort(key=lambda hit: (-hit[1], hit[0].slug))
    return hits[:limit]


def select_retrieval_strategy(question: str, requested: str, direct_hits: list[tuple[Page, int]]) -> tuple[str, str]:
    mode = (requested or "auto").lower()
    if mode not in RETRIEVAL_MODES:
        raise RuntimeError(f"Unsupported retrieval strategy: {requested}. Use one of: {', '.join(sorted(RETRIEVAL_MODES))}")
    if mode != "auto":
        complexity = "low" if mode in {"direct", "graph"} else "medium" if mode == "path" else "high"
        return mode, complexity

    lowered = question.lower()
    synthesis_terms = r"综合|总结|方案|策略|取舍|评估|对比|比较|tradeoff|strategy|evaluate|compare|synthesis|overall"
    path_terms = r"机制|流程|路径|关系|为什么|为何|如何|怎么|影响|依赖|适合|核心|区别|原因|mechanism|workflow|process|why|how|relationship|impact|depend|fit|core"
    if re.search(synthesis_terms, lowered):
        return "synthesis", "high"
    if re.search(path_terms, lowered):
        return "path", "medium"
    if len(direct_hits) <= 1:
        return "graph", "medium"
    top_score = direct_hits[0][1] if direct_hits else 0
    if top_score >= 8 and len(query_terms(question)) <= 4:
        return "direct", "low"
    return "graph", "medium"


def graph_neighbor_maps(graph: dict[str, object]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    incoming: dict[str, set[str]] = {}
    outgoing: dict[str, set[str]] = {}
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict) or not edge.get("target_exists"):
            continue
        source = str(edge["source"])
        target = str(edge["target"])
        outgoing.setdefault(source, set()).add(target)
        incoming.setdefault(target, set()).add(source)
    return incoming, outgoing


def graph_retrieval_hits(
    root: Path,
    pages: list[Page],
    question: str,
    top_k: int,
    retrieval: str,
    graph_rerank: bool = False,
    rerank_provider: str | None = None,
    rerank_model: str | None = None,
    rerank_api_key_env: str | None = None,
    rerank_base_url: str | None = None,
    rerank_max_output_tokens: int = 500,
) -> tuple[list[tuple[Page, int]], dict[str, object]]:
    direct_hits = find_hits(pages, question, limit=max(top_k, 1), include_relation_boost=False)
    strategy, complexity = select_retrieval_strategy(question, retrieval, direct_hits)
    pages_by_slug = {page.slug: page for page in pages}
    scores: dict[str, int] = {page.slug: score for page, score in direct_hits}
    direct_slugs = [page.slug for page, _ in direct_hits]
    expanded: dict[str, dict[str, str]] = {}
    path_evidence: list[list[str]] = []
    synthesis_slugs: list[str] = []
    fallback_from = ""
    fallback_reason = ""

    graph = build_wiki_graph(root)
    nodes = graph_nodes_by_id(graph)
    incoming, outgoing = graph_neighbor_maps(graph)

    def add_page(slug: str, score: int, reason: str, source: str) -> None:
        if slug not in pages_by_slug or slug in direct_slugs:
            return
        scores[slug] = max(scores.get(slug, 0), max(1, score))
        expanded.setdefault(slug, {"reason": reason, "source": source})

    if strategy in {"graph", "path", "synthesis"}:
        for page, score in direct_hits[: min(4, len(direct_hits))]:
            for target in sorted(outgoing.get(page.slug, set()))[:4]:
                add_page(target, round(score * 0.7), f"outbound neighbor of [[{page.slug}]]", "graph")
            for source in sorted(incoming.get(page.slug, set()))[:4]:
                add_page(source, round(score * 0.6), f"inbound neighbor of [[{page.slug}]]", "graph")

    if strategy in {"path", "synthesis"} and len(direct_slugs) >= 2:
        path_candidates = direct_slugs[: min(4, len(direct_slugs))]
        for start_index, start in enumerate(path_candidates):
            for goal in path_candidates[start_index + 1 :]:
                path = shortest_graph_path(graph, start, goal)
                if path and len(path) >= 2:
                    path_evidence.append(path)
                    if len(path) > 2:
                        for slug in path[1:-1]:
                            add_page(slug, max(2, round(scores.get(start, 2) * 0.55)), f"path bridge between [[{start}]] and [[{goal}]]", "path")

    if retrieval == "auto" and strategy == "path" and not path_evidence:
        fallback_from = "path"
        fallback_reason = "auto selected path, but no graph path evidence was found; fell back to graph retrieval"
        strategy = "graph"

    if strategy == "synthesis":
        for slug in ["overview", "synthesis"]:
            if slug in pages_by_slug:
                synthesis_slugs.append(slug)
                add_page(slug, 3, "global orientation/synthesis page", "synthesis")
        central_nodes = sorted(nodes.values(), key=lambda node: (-int(node.get("degree", 0)), str(node.get("id", ""))))[:3]
        for node in central_nodes:
            slug = str(node.get("id"))
            if slug in pages_by_slug:
                synthesis_slugs.append(slug)
                add_page(slug, 2, f"central graph node with degree {node.get('degree', 0)}", "synthesis")

    final_limit = top_k if strategy == "direct" else top_k + 2
    ordered_slugs = sorted(scores, key=lambda slug: (-scores[slug], 0 if slug in direct_slugs else 1, slug))[:final_limit]
    ordered_slugs, rerank_trace = maybe_llm_graph_rerank(
        root=root,
        question=question,
        ordered_slugs=ordered_slugs,
        pages_by_slug=pages_by_slug,
        scores=scores,
        direct_slugs=direct_slugs,
        expanded=expanded,
        path_evidence=path_evidence,
        synthesis_slugs=synthesis_slugs,
        strategy=strategy,
        enabled=graph_rerank,
        provider=rerank_provider,
        model=rerank_model,
        api_key_env=rerank_api_key_env,
        base_url=rerank_base_url,
        max_output_tokens=rerank_max_output_tokens,
    )
    hits = [(pages_by_slug[slug], scores[slug]) for slug in ordered_slugs]
    trace = {
        "requested_strategy": retrieval,
        "strategy": strategy,
        "complexity": complexity,
        "fallback_from": fallback_from,
        "fallback_reason": fallback_reason,
        "direct_hits": [{"slug": page.slug, "score": score, "file": page.rel} for page, score in direct_hits],
        "graph_expanded": [
            {
                "slug": slug,
                "score": scores.get(slug, 0),
                "reason": expanded[slug]["reason"],
                "source": expanded[slug]["source"],
                "file": pages_by_slug[slug].rel,
            }
            for slug in ordered_slugs
            if slug in expanded
        ],
        "path_evidence": path_evidence,
        "synthesis_pages": sorted(set(slug for slug in synthesis_slugs if slug in ordered_slugs)),
        "final_pages": [{"slug": page.slug, "score": score, "file": page.rel} for page, score in hits],
        "graph_rerank": rerank_trace,
    }
    return hits, trace


def graph_rerank_status(requested: bool, status: str = "not_requested", reason: str = "") -> dict[str, object]:
    return {
        "requested": requested,
        "status": status,
        "reason": reason,
        "provider": "",
        "model": "",
        "selected": [],
        "gaps": [],
        "prompt_version": "graph-rerank-v1",
    }


def int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def maybe_llm_graph_rerank(
    root: Path,
    question: str,
    ordered_slugs: list[str],
    pages_by_slug: dict[str, Page],
    scores: dict[str, int],
    direct_slugs: list[str],
    expanded: dict[str, dict[str, str]],
    path_evidence: list[list[str]],
    synthesis_slugs: list[str],
    strategy: str,
    enabled: bool,
    provider: str | None,
    model: str | None,
    api_key_env: str | None,
    base_url: str | None,
    max_output_tokens: int,
) -> tuple[list[str], dict[str, object]]:
    if not enabled:
        return ordered_slugs, graph_rerank_status(False)
    if strategy == "direct":
        return ordered_slugs, graph_rerank_status(True, "skipped", "graph rerank is only used for graph/path/synthesis retrieval")
    if len(ordered_slugs) < 2:
        return ordered_slugs, graph_rerank_status(True, "skipped", "not enough graph candidates to rerank")

    load_local_env(root)
    resolved_provider = (provider or os.environ.get("CWIKI_GRAPH_RERANK_PROVIDER") or os.environ.get("CWIKI_PROVIDER") or "openai").lower()
    if resolved_provider not in {"openai", "glm"}:
        return ordered_slugs, graph_rerank_status(True, "failed", f"unsupported provider: {resolved_provider}")
    resolved_model = model or os.environ.get("CWIKI_GRAPH_RERANK_MODEL") or resolve_model(resolved_provider, None)
    resolved_api_key_env = api_key_env or os.environ.get("CWIKI_GRAPH_RERANK_API_KEY_ENV") or resolve_api_key_env(resolved_provider, None)
    resolved_base_url = base_url or os.environ.get("CWIKI_GRAPH_RERANK_BASE_URL") or resolve_base_url(resolved_provider, None)
    api_key = os.environ.get(resolved_api_key_env)
    if not api_key:
        status = graph_rerank_status(True, "skipped", f"missing API key in {resolved_api_key_env}")
        status["provider"] = resolved_provider
        status["model"] = resolved_model
        return ordered_slugs, status

    candidates = graph_rerank_candidates(
        ordered_slugs,
        pages_by_slug,
        scores,
        direct_slugs,
        expanded,
        path_evidence,
        synthesis_slugs,
    )
    prompt = build_graph_rerank_prompt(question, strategy, candidates)
    instructions = (
        "You rerank graph retrieval candidates for an LLM Compound Wiki. "
        "Use only the supplied candidate metadata and return strict JSON only."
    )
    try:
        if resolved_provider == "openai":
            llm_response = call_openai_responses(api_key, resolved_model, instructions, prompt, max_output_tokens)
        else:
            llm_response = call_openai_compatible_chat(
                api_key=api_key,
                base_url=resolved_base_url,
                provider_name="GLM",
                model=resolved_model,
                instructions=instructions,
                prompt=prompt,
                max_output_tokens=max_output_tokens,
                extra_payload=graph_rerank_chat_options(resolved_provider),
            )
    except RuntimeError as error:
        status = graph_rerank_status(True, "failed", str(error))
        status["provider"] = resolved_provider
        status["model"] = resolved_model
        return ordered_slugs, status

    reranked, status = apply_llm_graph_rerank(ordered_slugs, llm_response.text)
    status["provider"] = resolved_provider
    status["model"] = resolved_model
    status["usage"] = llm_response.usage
    status["cost"] = llm_response.cost
    record_llm_usage(
        root,
        "graph-rerank",
        resolved_provider,
        resolved_model,
        llm_response,
        question=question,
        metadata={
            "retrieval_strategy": strategy,
            "candidate_count": len(ordered_slugs),
            "prompt_version": "graph-rerank-v1",
        },
    )
    return reranked, status


def graph_rerank_candidates(
    ordered_slugs: list[str],
    pages_by_slug: dict[str, Page],
    scores: dict[str, int],
    direct_slugs: list[str],
    expanded: dict[str, dict[str, str]],
    path_evidence: list[list[str]],
    synthesis_slugs: list[str],
) -> list[dict[str, object]]:
    path_slugs = {slug for path in path_evidence for slug in path}
    candidates: list[dict[str, object]] = []
    for slug in ordered_slugs:
        page = pages_by_slug[slug]
        roles = []
        reasons = []
        if slug in direct_slugs:
            roles.append("direct")
            reasons.append("direct retrieval hit")
        if slug in expanded:
            roles.append(str(expanded[slug].get("source", "graph")))
            reasons.append(str(expanded[slug].get("reason", "")))
        if slug in path_slugs:
            roles.append("path")
            reasons.append("appears in path evidence")
        if slug in synthesis_slugs:
            roles.append("synthesis")
            reasons.append("global or central synthesis context")
        candidates.append(
            {
                "slug": slug,
                "title": page.title,
                "file": page.rel,
                "kind": page.kind,
                "tags": page.tags,
                "score": scores.get(slug, 0),
                "roles": sorted(set(role for role in roles if role)),
                "reasons": [reason for reason in reasons if reason],
                "summary": page.summary,
            }
        )
    return candidates


def build_graph_rerank_prompt(question: str, strategy: str, candidates: list[dict[str, object]]) -> str:
    candidate_text = "\n".join(
        f"""## Candidate {index}: [[{candidate['slug']}]]

- Title: {candidate.get('title')}
- File: `{candidate.get('file')}`
- Kind: {candidate.get('kind')}
- Tags: {candidate.get('tags') or '-'}
- Deterministic score: {candidate.get('score', 0)}
- Retrieval roles: {', '.join(candidate.get('roles', [])) or '-'}
- Retrieval reasons: {'; '.join(candidate.get('reasons', [])) or '-'}
- Summary: {candidate.get('summary') or '-'}
"""
        for index, candidate in enumerate(candidates, start=1)
    )
    return f"""# LLM Graph Rerank Request

Question: {question}
Retrieval strategy: {strategy}

You are reranking final context candidates from a graph-aware retrieval step.
Prefer pages that directly help answer the question, then pages that explain relationships, paths, mechanisms, dependencies, or synthesis context.
Use only the candidate metadata below. Do not invent facts.

Return strict JSON with this shape:

```json
{{
  "selected": [
    {{"slug": "page-slug", "rank": 1, "reason": "why this candidate should be earlier"}}
  ],
  "gaps": ["missing evidence or graph limitations"]
}}
```

Rank at most {len(candidates)} candidates. Omitted candidates will keep deterministic order after selected candidates.

## Candidates

{candidate_text or '- No candidates.'}
"""


def extract_json_object(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def apply_llm_graph_rerank(ordered_slugs: list[str], llm_text: str) -> tuple[list[str], dict[str, object]]:
    status = graph_rerank_status(True)
    payload = extract_json_object(llm_text)
    if not payload:
        status["status"] = "failed"
        status["reason"] = "LLM response was not parseable JSON; deterministic order retained"
        return ordered_slugs, status

    by_slug = {slug: slug for slug in ordered_slugs}
    selected = payload.get("selected")
    selected_rows: list[dict[str, object]] = []
    reranked: list[str] = []
    if isinstance(selected, list):
        for item in selected:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", ""))
            if slug not in by_slug or slug in reranked:
                continue
            reranked.append(slug)
            selected_rows.append(
                {
                    "slug": slug,
                    "rank": int_or_none(item.get("rank")) or len(reranked),
                    "reason": str(item.get("reason", "")).strip(),
                }
            )
    if not reranked:
        status["status"] = "failed"
        status["reason"] = "LLM response did not select any known candidate; deterministic order retained"
        return ordered_slugs, status

    reranked.extend(slug for slug in ordered_slugs if slug not in reranked)
    gaps = payload.get("gaps")
    status["status"] = "completed"
    status["selected"] = selected_rows
    status["gaps"] = [str(gap) for gap in gaps] if isinstance(gaps, list) else []
    return reranked, status


def graph_rerank_chat_options(provider: str) -> dict[str, object]:
    options: dict[str, object] = {}
    thinking = os.environ.get("CWIKI_GRAPH_RERANK_THINKING")
    if thinking is None and provider == "glm":
        thinking = "disabled"
    if thinking and thinking.strip():
        options["thinking"] = {"type": thinking.strip().lower()}
    return options


def render_retrieval_trace(trace: dict[str, object]) -> str:
    direct = trace.get("direct_hits", [])
    expanded = trace.get("graph_expanded", [])
    paths = trace.get("path_evidence", [])
    synthesis_pages = trace.get("synthesis_pages", [])
    final_pages = trace.get("final_pages", [])
    fallback_reason = str(trace.get("fallback_reason", "") or "")
    rerank = trace.get("graph_rerank") if isinstance(trace.get("graph_rerank"), dict) else graph_rerank_status(False)

    direct_lines = "\n".join(f"- [[{item['slug']}]] ({item['score']}) `{item['file']}`" for item in direct) if direct else "- None"
    expanded_lines = (
        "\n".join(f"- [[{item['slug']}]] ({item['score']}) `{item['file']}` - {item['reason']}" for item in expanded)
        if expanded
        else "- None"
    )
    path_lines = "\n".join("- " + " -> ".join(f"[[{slug}]]" for slug in path) for path in paths) if paths else "- None"
    synthesis_lines = "\n".join(f"- [[{slug}]]" for slug in synthesis_pages) if synthesis_pages else "- None"
    final_lines = "\n".join(f"- [[{item['slug']}]] ({item['score']}) `{item['file']}`" for item in final_pages) if final_pages else "- None"
    rerank_selected = rerank.get("selected") if isinstance(rerank, dict) else []
    rerank_lines = (
        "\n".join(f"- [[{item.get('slug')}]] rank={item.get('rank')} - {item.get('reason') or '-'}" for item in rerank_selected if isinstance(item, dict))
        if isinstance(rerank_selected, list) and rerank_selected
        else "- None"
    )
    rerank_gaps = rerank.get("gaps") if isinstance(rerank, dict) else []
    rerank_gap_lines = "\n".join(f"- {gap}" for gap in rerank_gaps) if isinstance(rerank_gaps, list) and rerank_gaps else "- None"
    rerank_usage = rerank.get("usage") if isinstance(rerank.get("usage"), dict) else None
    rerank_cost = rerank.get("cost") if isinstance(rerank.get("cost"), dict) else None
    rerank_usage_lines = llm_usage_bullets(rerank_usage, rerank_cost) if rerank_usage or rerank_cost else "- Usage: unavailable"
    return f"""## Retrieval Trace

- Requested strategy: {trace.get('requested_strategy', 'auto')}
- Strategy used: {trace.get('strategy', 'direct')}
- Complexity: {trace.get('complexity', 'low')}
- Direct hit count: {len(direct)}
- Graph-expanded page count: {len(expanded)}
- Path evidence count: {len(paths)}
- Graph rerank requested: {str(rerank.get('requested', False)).lower()}
- Graph rerank status: {rerank.get('status', 'not_requested')}
{f"- Graph rerank note: {rerank.get('reason')}" if rerank.get('reason') else ""}
{f"- Fallback: {fallback_reason}" if fallback_reason else ""}

### Direct Hits

{direct_lines}

### Graph-Expanded Pages

{expanded_lines}

### Path Evidence

{path_lines}

### Synthesis Pages

{synthesis_lines}

### LLM Graph Rerank

- Provider: `{rerank.get('provider') or '-'}`
- Model: `{rerank.get('model') or '-'}`
{rerank_usage_lines}

Selected:

{rerank_lines}

Gaps:

{rerank_gap_lines}

### Final Context Pages

{final_lines}
"""


def expand_terms(terms: list[str]) -> list[str]:
    expanded: list[str] = []
    for term in terms:
        expanded.append(term)
        expanded.extend(SYNONYM_SEEDS.get(term, []))
    seen: set[str] = set()
    deduped: list[str] = []
    for term in expanded:
        lowered = term.lower()
        if lowered not in seen:
            seen.add(lowered)
            deduped.append(lowered)
    return deduped


def query_terms(query: str) -> list[str]:
    normalized = query.lower().strip()
    raw_terms = re.findall(r"[a-z0-9]+|[\u4e00-\u9fa5]{2,}", normalized)
    terms: list[str] = []
    for term in raw_terms:
        if term in STOPWORDS:
            continue
        if re.fullmatch(r"[\u4e00-\u9fa5]{3,}", term):
            grams = [term[i : i + 2] for i in range(len(term) - 1)]
            terms.extend(gram for gram in grams if gram not in STOPWORDS)
        else:
            terms.append(term)

    # Preserve order while deduplicating.
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            deduped.append(term)
    return deduped


def semantic_tokens(text: str) -> list[str]:
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9_+-]+|[\u4e00-\u9fa5]{2,}", normalized)
    result: list[str] = []
    for token in tokens:
        if token in STOPWORDS:
            continue
        result.append(token)
        if re.fullmatch(r"[\u4e00-\u9fa5]{3,}", token):
            result.extend(token[i : i + 2] for i in range(len(token) - 1))
    return result


def text_vector(text: str, dimensions: int = VECTOR_DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    for token in semantic_tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    return vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    if dot == 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, dot / (left_norm * right_norm))


def compact_page_context(page: Page, max_chars: int = 3500) -> str:
    text = page.text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n... [truncated for prompt context]"


def create_query_prompt(
    target: str,
    question: str,
    top_k: int = DEFAULT_TOP_K,
    retrieval: str = "auto",
    graph_rerank: bool = False,
    rerank_provider: str | None = None,
    rerank_model: str | None = None,
    rerank_api_key_env: str | None = None,
    rerank_base_url: str | None = None,
    rerank_max_output_tokens: int = 500,
) -> tuple[Path, Path, list[tuple[Page, int]], str, str]:
    root = Path(target).resolve()
    assert_wiki(root)
    pages = collect_pages(root)
    hits, trace = graph_retrieval_hits(
        root,
        pages,
        question,
        top_k,
        retrieval,
        graph_rerank,
        rerank_provider,
        rerank_model,
        rerank_api_key_env,
        rerank_base_url,
        rerank_max_output_tokens,
    )
    date = today()
    slug = slugify(question)
    ensure_dir(root / ".cwiki" / "prompts")
    ensure_dir(root / ".cwiki" / "briefs")
    prompt_file = root / ".cwiki" / "prompts" / f"query-{date}-{slug}.md"
    brief_file = root / ".cwiki" / "briefs" / f"brief-{date}-{slug}.md"

    if hits:
        context_sections = "\n\n".join(
            f"""## [[{page.slug}]] — {page.title}

- File: `{page.rel}`
- Kind: `{page.kind}`
- Tags: {page.tags or "-"}
- Updated: {page.updated or "-"}
- Search score: {score}

```markdown
{compact_page_context(page)}
```"""
            for page, score in hits
        )
        relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}`" for page, score in hits)
    else:
        context_sections = "No directly matching wiki pages were found. Read `wiki/index.md` and decide whether the wiki has enough information."
        relevant_pages = "- No direct matches"

    prompt = f"""---
title: Query Prompt - {question}
tags: [query, prompt]
sources: {len(hits)}
updated: {date}
status: pending
retrieval_strategy: {trace.get('strategy', 'direct')}
retrieval_requested: {trace.get('requested_strategy', retrieval)}
retrieval_complexity: {trace.get('complexity', 'low')}
retrieval_direct_hits: {len(trace.get('direct_hits', []))}
retrieval_graph_expanded: {len(trace.get('graph_expanded', []))}
retrieval_path_count: {len(trace.get('path_evidence', []))}
retrieval_fallback_from: {trace.get('fallback_from', '')}
retrieval_fallback_reason: {trace.get('fallback_reason', '')}
retrieval_graph_rerank: {(trace.get('graph_rerank') or {}).get('status', 'not_requested') if isinstance(trace.get('graph_rerank'), dict) else 'not_requested'}
---

# Query Prompt - {question}

## Question

{question}

## Relevant Pages

{relevant_pages}

{render_retrieval_trace(trace)}

## Instructions For The Agent

1. Read `CLAUDE.md` and `WIKI_SCHEMA.md`.
2. Read `wiki/index.md`.
3. Read the relevant pages below in full from disk before answering.
4. Treat this prompt as the reproducible evidence boundary. If the context pack is enough, answer directly from it.
5. Read Retrieval Trace as the layered retrieval contract: Direct Hits are primary evidence; Graph-Expanded Pages are nearby graph context; Path Evidence explains relationships; Final Context Pages are the bounded context pack.
6. If Strategy used is `graph`, use graph-expanded pages only when they materially support the answer; otherwise mark them `not used - reason`.
7. If Strategy used is `path`, explicitly check Path Evidence. If it is missing or weak, fall back mentally to graph/direct evidence and state that limitation in `## Gaps`.
8. If the context pack looks incomplete, use the hybrid agent workflow: search or inspect `wiki/index.md`, read additional high-signal wiki pages, and follow one level of useful `[[wikilinks]]`.
9. If the question needs current web evidence, do not guess from memory. Use `cwiki web-ask . "<question>"` or `wiki-agent-browser`, then cite opened sources with URLs and access dates.
10. Use this output structure: `## Evidence Used`, `## Answer`, `## Gaps`.
11. In `## Evidence Used`, list every Relevant Page. For each page, write either `- [[slug]] - used - source: raw/...` or `- [[slug]] - not used - reason: ...`. Also list any extra wiki pages or web sources found during hybrid exploration.
12. In `## Answer`, cite the wiki pages you actually use with local citations like `[[slug]]`, and keep source paths or URLs near factual claims.
13. Use the relevant pages that materially support the answer. If a listed Relevant Page is not useful, mention that in `## Gaps`.
14. Always include a `## Gaps` section. State missing evidence, weak coverage, unused relevant pages, hybrid exploration limits, or other limitations. If no gaps are known, write that explicitly.
15. If the answer is valuable, offer to save it into `wiki/synthesis.md`, `wiki/comparisons/`, or another fitting wiki page.
16. If saved, run `cwiki index .` and append to `wiki/log.md`.

## Context Pack

{context_sections}
"""
    prompt_file.write_text(prompt, encoding="utf-8")
    brief = render_human_brief(question, hits, trace)
    brief_file.write_text(brief, encoding="utf-8")
    return prompt_file, brief_file, hits, prompt, brief


def render_human_brief(question: str, hits: list[tuple[Page, int]], trace: dict[str, object] | None = None) -> str:
    date = today()
    chinese = contains_chinese(question) or any(contains_chinese(page.text) for page, _ in hits)
    if not hits:
        if chinese:
            return f"""---
title: Brief - {question}
tags: [query, brief]
sources: 0
updated: {date}
status: draft
---

# Brief - {question}

没有找到直接匹配的 wiki 页面。请先运行 `cwiki index .`、检查 `wiki/index.md`，或继续摄入更多来源后再期待有依据的回答。
"""
        return f"""---
title: Brief - {question}
tags: [query, brief]
sources: 0
updated: {date}
status: draft
---

# Brief - {question}

No directly matching wiki pages were found. Run `cwiki index .`, inspect `wiki/index.md`, or ingest more sources before expecting a grounded answer.
"""

    relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}` — {page.summary}" for page, score in hits)
    claims = "\n".join(extract_claim_bullets(page) for page, _ in hits)
    syntheses = "\n".join(extract_section_bullet(page, "Synthesis") for page, _ in hits)
    if not syntheses:
        syntheses = "\n".join(extract_section_bullet(page, "综合结论") for page, _ in hits)
    open_questions = "\n".join(extract_section_bullet(page, "Open Questions") for page, _ in hits)
    if not open_questions:
        open_questions = "\n".join(extract_section_bullet(page, "开放问题") for page, _ in hits)
    trace_zh = ""
    trace_en = ""
    if trace:
        fallback_reason = str(trace.get("fallback_reason", "") or "")
        fallback_zh = f"- 回退：{fallback_reason}\n" if fallback_reason else ""
        fallback_en = f"- Fallback: {fallback_reason}\n" if fallback_reason else ""
        rerank = trace.get("graph_rerank") if isinstance(trace.get("graph_rerank"), dict) else graph_rerank_status(False)
        rerank_reason = str(rerank.get("reason", "") or "")
        rerank_zh = f"- LLM 图重排：{rerank.get('status', 'not_requested')}{f'（{rerank_reason}）' if rerank_reason else ''}\n"
        rerank_en = f"- LLM graph rerank: {rerank.get('status', 'not_requested')}{f' ({rerank_reason})' if rerank_reason else ''}\n"
        trace_zh = f"""
## 检索轨迹

- 策略：{trace.get('strategy', 'direct')}
- 复杂度：{trace.get('complexity', 'low')}
- 直接命中：{len(trace.get('direct_hits', []))}
- 图谱扩展：{len(trace.get('graph_expanded', []))}
- 路径证据：{len(trace.get('path_evidence', []))}
{rerank_zh}{fallback_zh}"""
        trace_en = f"""
## Retrieval Trace

- Strategy: {trace.get('strategy', 'direct')}
- Complexity: {trace.get('complexity', 'low')}
- Direct hits: {len(trace.get('direct_hits', []))}
- Graph-expanded pages: {len(trace.get('graph_expanded', []))}
- Path evidence: {len(trace.get('path_evidence', []))}
{rerank_en}{fallback_en}"""

    if chinese:
        return f"""---
title: Brief - {question}
tags: [query, brief]
sources: {len(hits)}
updated: {date}
status: draft
---

# Brief - {question}

这是从已编译 wiki 中确定性生成的证据摘要，比模型 prompt 更适合快速阅读，但还不是完整的大模型回答。

## 问题

{question}

## 简短结论

wiki 中有 {len(hits)} 个相关页面。建议先读 {', '.join(f'[[{page.slug}]]' for page, _ in hits[:3])}。

## 相关页面

{relevant_pages}
{trace_zh}

## 关键声明

{claims or '- 匹配页面中没有找到 Claim Ledger 行。'}

## 既有综合

{syntheses or '- 匹配页面中没有找到综合结论章节。'}

## 开放问题与缺口

{open_questions or '- 匹配页面中没有显式开放问题。'}

## 下一步

如需完整答案，运行 `cwiki answer` 并配置 API key，或把 `.cwiki/prompts/query-*.md` 交给 agent。
"""

    return f"""---
title: Brief - {question}
tags: [query, brief]
sources: {len(hits)}
updated: {date}
status: draft
---

# Brief - {question}

This is a deterministic evidence brief generated from the compiled wiki. It is more readable than the model prompt, but it is not a full LLM-written answer.

## Question

{question}

## Short Takeaway

The wiki has relevant material in {len(hits)} page(s). Start with {', '.join(f'[[{page.slug}]]' for page, _ in hits[:3])}.

## Relevant Pages

{relevant_pages}
{trace_en}

## Key Claims

{claims or '- No claim ledger rows found in the matched pages.'}

## Existing Synthesis

{syntheses or '- No synthesis sections found in the matched pages.'}

## Open Questions And Gaps

{open_questions or '- No explicit open questions found in the matched pages.'}

## Next Step

For a polished answer, run `cwiki answer` with an API key or give `.cwiki/prompts/query-*.md` to an agent.
"""


def contains_chinese(text: str) -> bool:
    return re.search(r"[\u4e00-\u9fa5]", text) is not None


def extract_claim_bullets(page: Page, max_claims: int = 4) -> str:
    lines = page.text.splitlines()
    in_ledger = False
    claims: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_ledger = stripped.lower() == "## claim ledger"
            continue
        if not in_ledger or not stripped.startswith("|") or stripped.startswith("|---") or "Claim" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells:
            claims.append(f"- [[{page.slug}]]: {cells[0]}")
        if len(claims) >= max_claims:
            break
    return "\n".join(claims)


def extract_section_bullet(page: Page, heading: str, max_chars: int = 420) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", flags=re.IGNORECASE | re.MULTILINE)
    match = pattern.search(page.text)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", page.text[start:], flags=re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(page.text)
    body = re.sub(r"\s+", " ", page.text[start:end].strip())
    if not body:
        return ""
    return f"- [[{page.slug}]]: {body[:max_chars]}"


def ask_wiki(
    target: str,
    question: str,
    top_k: int = DEFAULT_TOP_K,
    show_context: bool = False,
    retrieval: str = "auto",
    graph_rerank: bool = False,
    provider: str | None = None,
    model: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    graph_rerank_output_tokens: int = 500,
) -> None:
    root = Path(target).resolve()
    prompt_file, brief_file, hits, prompt, brief = create_query_prompt(
        target,
        question,
        top_k,
        retrieval,
        graph_rerank,
        provider,
        model,
        api_key_env,
        base_url,
        graph_rerank_output_tokens,
    )
    print(f"Created query prompt: {prompt_file.relative_to(root).as_posix()}")
    print(f"Created human brief: {brief_file.relative_to(root).as_posix()}")
    if hits:
        print("Relevant pages:")
        for page, score in hits:
            print(f"- [[{page.slug}]] ({score}) {page.rel}")
    else:
        print("Relevant pages: no direct matches")
    if show_context:
        print("\n--- Human Brief ---")
        print(brief)
        print("\n--- Query Prompt ---")
        print(prompt)


def render_research_focus_section(research_focus: str, language: str = "en") -> str:
    if not research_focus:
        return ""
    heading = "研究重点" if language == "zh-CN" else "Research Focus"
    return f"## {heading}\n\n{research_focus}\n"


def create_web_query_prompt(
    target: str,
    question: str,
    top_k: int = DEFAULT_TOP_K,
    max_web_sources: int = 6,
    wiki_weight: float = DEFAULT_WIKI_WEIGHT,
    web_weight: float = DEFAULT_WEB_WEIGHT,
    web_enabled: bool = True,
    research_focus: str = "",
) -> tuple[Path, Path, Path, Path, list[tuple[Page, int]], str, str]:
    root = Path(target).resolve()
    assert_wiki(root)
    validate_weights(wiki_weight, web_weight)
    pages = collect_pages(root)
    hits = find_hits(pages, question, limit=top_k)
    date = today()
    slug = slugify(question)
    ensure_dir(root / ".cwiki" / "prompts")
    ensure_dir(root / ".cwiki" / "briefs")
    ensure_dir(root / ".cwiki" / "web-research")
    prompt_file = root / ".cwiki" / "prompts" / f"web-query-{date}-{slug}.md"
    fusion_prompt_file = root / ".cwiki" / "prompts" / f"fusion-{date}-{slug}.md"
    brief_file = root / ".cwiki" / "briefs" / f"web-brief-{date}-{slug}.md"
    research_file = root / ".cwiki" / "web-research" / f"web-research-{date}-{slug}.md"
    effective_web_sources = max_web_sources if web_enabled and web_weight > 0 else 0
    web_mode = "enabled" if effective_web_sources > 0 else "disabled"

    if hits:
        context_sections = "\n\n".join(
            f"""## [[{page.slug}]] — {page.title}

- File: `{page.rel}`
- Kind: `{page.kind}`
- Tags: {page.tags or "-"}
- Updated: {page.updated or "-"}
- Search score: {score}

```markdown
{compact_page_context(page)}
```"""
            for page, score in hits
        )
        relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}`" for page, score in hits)
    else:
        context_sections = "No directly matching wiki pages were found. Use `wiki/index.md` to understand the local wiki before browsing."
        relevant_pages = "- No direct matches"

    focus_section = render_research_focus_section(research_focus)
    prompt = f"""---
title: Web Query Prompt - {question}
tags: [query, web, prompt]
sources: {len(hits)}
updated: {date}
status: pending
wiki_weight: {wiki_weight}
web_weight: {web_weight}
web_mode: {web_mode}
---

# Web Query Prompt - {question}

## Question

{question}

{focus_section}
## Local Wiki Context

{relevant_pages}

## Agent Browser Protocol

Use the `wiki-agent-browser` skill. Combine the local wiki with current web evidence, but keep the layers distinguishable.

Evidence weights for final synthesis:

- Local wiki weight: {wiki_weight}
- Web search weight: {web_weight}
- Web mode: {web_mode}

If web mode is `disabled`, do not search the web. Use local wiki evidence only and state that web evidence was intentionally disabled.

1. Read `CLAUDE.md`, `WIKI_SCHEMA.md`, and `wiki/index.md`.
2. Read the relevant local pages below in full from disk before answering.
3. Search the web for up to {effective_web_sources} high-quality sources that materially affect the answer.
4. Prefer primary sources, official documentation, standards, filings, papers, release notes, or reputable data providers.
5. Open and inspect each cited web source. Do not cite search result snippets as evidence.
6. For every external factual claim, cite a URL and include the access date `{date}`.
7. Write findings into `{research_file.relative_to(root).as_posix()}`.
8. Then use `{fusion_prompt_file.relative_to(root).as_posix()}` to produce the final answer.
9. Separate `Local wiki evidence`, `Web evidence`, `Synthesis`, `Gaps`, and `Sources`.
10. If web evidence should become durable wiki knowledge, first run `cwiki capture . <url> --title "<title>"`, then process the generated ingest prompt with user approval.
11. Do not silently overwrite local wiki conclusions with web results. Call out conflicts and uncertainty.

## Required Source Table

| Title | URL | Publisher / Author | Accessed | Why it matters |
|---|---|---|---|---|
|  |  |  | {date} |  |

## Context Pack

{context_sections}
"""
    prompt_file.write_text(prompt, encoding="utf-8")
    research = render_web_research_template(question, hits, wiki_weight, web_weight, web_mode, effective_web_sources, research_focus)
    research_file.write_text(research, encoding="utf-8")
    fusion_prompt = render_fusion_prompt(question, hits, research_file, wiki_weight, web_weight, web_mode, research_focus)
    fusion_prompt_file.write_text(fusion_prompt, encoding="utf-8")
    brief = render_web_brief(question, hits, prompt_file, fusion_prompt_file, research_file, effective_web_sources, wiki_weight, web_weight, web_mode, research_focus)
    brief_file.write_text(brief, encoding="utf-8")
    return prompt_file, brief_file, research_file, fusion_prompt_file, hits, prompt, brief


def validate_weights(wiki_weight: float, web_weight: float) -> None:
    if wiki_weight < 0 or web_weight < 0:
        raise RuntimeError("Evidence weights must be non-negative.")
    if wiki_weight == 0 and web_weight == 0:
        raise RuntimeError("At least one evidence weight must be greater than 0.")


def render_weight_guidance(wiki_weight: float, web_weight: float, web_mode: str) -> str:
    if web_mode == "disabled" or web_weight == 0:
        return "Web evidence is disabled. Use local wiki evidence only, and state that no web search was requested."
    if web_weight > wiki_weight:
        return "Web evidence has higher synthesis weight, but it still must be traceable and checked against local wiki context."
    if wiki_weight > web_weight:
        return "Local wiki evidence has higher synthesis weight. Use web evidence mainly to update, verify, or challenge local conclusions."
    return "Local wiki evidence and web evidence have equal synthesis weight. Reconcile conflicts explicitly."


def render_web_research_template(
    question: str,
    hits: list[tuple[Page, int]],
    wiki_weight: float,
    web_weight: float,
    web_mode: str,
    max_web_sources: int,
    research_focus: str = "",
) -> str:
    date = today()
    relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}` — {page.summary}" for page, score in hits)
    if not relevant_pages:
        relevant_pages = "- No direct local matches"
    focus_section = render_research_focus_section(research_focus)
    return f"""---
title: Web Research - {question}
tags: [query, web-research]
sources: 0
updated: {date}
status: pending
wiki_weight: {wiki_weight}
web_weight: {web_weight}
web_mode: {web_mode}
---

# Web Research - {question}

This is the browser research workspace. Fill it before producing the final answer from the fusion prompt.

## Question

{question}

{focus_section}
## Evidence Weights

- Local wiki weight: {wiki_weight}
- Web search weight: {web_weight}
- Web mode: {web_mode}
- Guidance: {render_weight_guidance(wiki_weight, web_weight, web_mode)}

## Local Wiki Evidence

{relevant_pages}

## Web Search Plan

- Max web sources: {max_web_sources}
- If max web sources is `0`, do not browse.
- Prefer primary sources and durable references.
- Open each source before citing it.

## Web Sources

| Title | URL | Publisher / Author | Published | Accessed | Why it matters |
|---|---|---|---|---|---|

## Extracted Web Claims

| Claim | Source URL | Confidence | Last checked |
|---|---|---:|---|

## Conflicts With Local Wiki

- None recorded yet.

## Synthesis Notes

- Pending browser research.

## Gaps

- Pending browser research.

## Recommended Captures

- Add `cwiki capture . <url> --title "<title>"` commands for durable web sources worth ingesting.
"""


def render_fusion_prompt(
    question: str,
    hits: list[tuple[Page, int]],
    research_file: Path,
    wiki_weight: float,
    web_weight: float,
    web_mode: str,
    research_focus: str = "",
) -> str:
    date = today()
    relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}`" for page, score in hits)
    if not relevant_pages:
        relevant_pages = "- No direct local matches"
    focus_section = render_research_focus_section(research_focus)
    return f"""---
title: Evidence Fusion Prompt - {question}
tags: [query, fusion, prompt]
sources: {len(hits)}
updated: {date}
status: pending
wiki_weight: {wiki_weight}
web_weight: {web_weight}
web_mode: {web_mode}
---

# Evidence Fusion Prompt - {question}

## Question

{question}

{focus_section}
## Evidence Inputs

### Local Wiki Pages

{relevant_pages}

### Web Research File

`{research_file.as_posix()}`

## Fusion Policy

- Local wiki weight: {wiki_weight}
- Web search weight: {web_weight}
- Web mode: {web_mode}
- Guidance: {render_weight_guidance(wiki_weight, web_weight, web_mode)}

## Instructions For The Answering Agent

1. Read `CLAUDE.md`, `WIKI_SCHEMA.md`, and `wiki/index.md`.
2. Read the local wiki pages listed above in full.
3. Read the web research file after browser research has been completed.
4. If web mode is `disabled`, do not browse and ignore empty web sections.
5. Produce a final answer with sections for local wiki evidence, web evidence, synthesis, gaps, and sources.
6. Use local citations like `[[slug]]` and source paths from claim ledgers.
7. Use Markdown links for web sources and include access dates from the research file.
8. If local and web evidence conflict, explain the conflict and which source has more weight under the configured policy.
9. Do not write the final answer into `wiki/` unless the user asks to preserve it.
"""


def render_web_brief(
    question: str,
    hits: list[tuple[Page, int]],
    prompt_file: Path,
    fusion_prompt_file: Path,
    research_file: Path,
    max_web_sources: int,
    wiki_weight: float,
    web_weight: float,
    web_mode: str,
    research_focus: str = "",
) -> str:
    date = today()
    chinese = contains_chinese(question) or any(contains_chinese(page.text) for page, _ in hits)
    relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}` — {page.summary}" for page, score in hits)
    if not relevant_pages:
        relevant_pages = "- No direct local matches"

    if chinese:
        focus_section = render_research_focus_section(research_focus, "zh-CN")
        return f"""---
title: Web Brief - {question}
tags: [query, web, brief]
sources: {len(hits)}
updated: {date}
status: draft
---

# Web Brief - {question}

这是一份联网研究任务摘要，不是最终答案。它会把本地 wiki 相关页面和网络检索要求放在一起，交给具备浏览器/搜索能力的 agent 执行。

## 问题

{question}

{focus_section}
## 本地相关页面

{relevant_pages}

## 联网要求

- 最多选择 {max_web_sources} 个高质量网络来源。
- 证据权重：本地 wiki `{wiki_weight}`，web search `{web_weight}`，web mode `{web_mode}`。
- {render_weight_guidance(wiki_weight, web_weight, web_mode)}
- 必须打开来源正文后再引用，不要引用搜索结果摘要。
- 外部事实必须带 URL、发布方/作者和访问日期 `{date}`。
- 回答时区分本地 wiki 证据、网络证据、综合结论和缺口。
- 值得沉淀的网络来源先用 `cwiki capture` 记录到 `raw/captures/`，再由 agent 摄入到 `wiki/`。

## 中间产物

- Web query prompt: `{prompt_file.name}`
- Web research workspace: `{research_file.name}`
- Evidence fusion prompt: `{fusion_prompt_file.name}`
"""

    focus_section = render_research_focus_section(research_focus)
    return f"""---
title: Web Brief - {question}
tags: [query, web, brief]
sources: {len(hits)}
updated: {date}
status: draft
---

# Web Brief - {question}

This is a web research task brief, not a final answer. It combines local wiki context with explicit browser research requirements for a browser-capable agent.

## Question

{question}

{focus_section}
## Relevant Local Pages

{relevant_pages}

## Web Requirements

- Select up to {max_web_sources} high-quality web sources.
- Evidence weights: local wiki `{wiki_weight}`, web search `{web_weight}`, web mode `{web_mode}`.
- {render_weight_guidance(wiki_weight, web_weight, web_mode)}
- Open the source body before citing it; do not cite search snippets.
- External factual claims need a URL, publisher/author, and access date `{date}`.
- Separate local wiki evidence, web evidence, synthesis, and gaps.
- Durable web sources should be captured with `cwiki capture` before ingesting them into `wiki/`.

## Artifacts

- Web query prompt: `{prompt_file.name}`
- Web research workspace: `{research_file.name}`
- Evidence fusion prompt: `{fusion_prompt_file.name}`
"""


def web_ask_wiki(
    target: str,
    question: str,
    top_k: int = DEFAULT_TOP_K,
    max_web_sources: int | None = None,
    wiki_weight: float | None = None,
    web_weight: float | None = None,
    no_web: bool = False,
    show_context: bool = False,
) -> None:
    root = Path(target).resolve()
    load_local_env(root)
    resolved_wiki_weight = wiki_weight if wiki_weight is not None else env_float("CWIKI_WEB_WIKI_WEIGHT", DEFAULT_WIKI_WEIGHT)
    resolved_web_weight = web_weight if web_weight is not None else env_float("CWIKI_WEB_WEIGHT", DEFAULT_WEB_WEIGHT)
    resolved_max_web_sources = (
        max_web_sources if max_web_sources is not None else env_int("CWIKI_WEB_MAX_SOURCES", 6)
    )
    env_web_enabled = env_bool("CWIKI_WEB_ENABLED", True)
    if no_web:
        env_web_enabled = False
    web_enabled = env_web_enabled and resolved_web_weight > 0 and resolved_max_web_sources > 0
    prompt_file, brief_file, research_file, fusion_prompt_file, hits, prompt, brief = create_web_query_prompt(
        target,
        question,
        top_k,
        resolved_max_web_sources,
        resolved_wiki_weight,
        resolved_web_weight,
        web_enabled,
    )
    print(f"Created web query prompt: {prompt_file.relative_to(root).as_posix()}")
    print(f"Created web brief: {brief_file.relative_to(root).as_posix()}")
    print(f"Created web research workspace: {research_file.relative_to(root).as_posix()}")
    print(f"Created evidence fusion prompt: {fusion_prompt_file.relative_to(root).as_posix()}")
    print(f"Evidence weights: wiki={resolved_wiki_weight}, web={resolved_web_weight}, web_mode={'enabled' if web_enabled else 'disabled'}")
    if web_enabled:
        print("Next: give the web query prompt to a browser-capable agent using `wiki-agent-browser`; the CLI does not browse by itself.")
    if hits:
        print("Relevant local pages:")
        for page, score in hits:
            print(f"- [[{page.slug}]] ({score}) {page.rel}")
    else:
        print("Relevant local pages: no direct matches")
    if show_context:
        print("\n--- Web Brief ---")
        print(brief)
        print("\n--- Web Query Prompt ---")
        print(prompt)


WEB_GAP_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        "case_studies",
        r"case stud|real[- ]world|industry|enterprise|customer|production|案例|落地|行业|真实|实践|客户|企业",
        "缺少真实案例、行业对比或落地证据",
        "Missing case studies, industry comparisons, or real-world evidence",
    ),
    (
        "metrics",
        r"metric|benchmark|latency|cost|roi|throughput|accuracy|performance|quant|量化|指标|成本|延迟|吞吐|准确率|性能|ROI|开销",
        "缺少量化指标、成本、性能或 ROI 对比",
        "Missing quantitative metrics, cost, performance, or ROI comparisons",
    ),
    (
        "migration",
        r"migration|transition|implementation|roadmap|playbook|guide|迁移|过渡|实施|指南|路径|步骤|落地方案",
        "缺少迁移路径、实施指南或落地步骤",
        "Missing migration path, implementation guide, or rollout steps",
    ),
    (
        "current_external",
        r"latest|recent|current|today|web|online|external|market|policy|regulation|最新|近期|当前|今天|联网|网络|外部|市场|政策|监管",
        "缺少最新、外部或联网证据",
        "Missing current, external, or web evidence",
    ),
]


def create_web_followup_for_answer_gaps(
    root: Path,
    answer_file: Path,
    eval_result: dict[str, object],
    top_k: int,
    max_web_sources: int | None,
    wiki_weight: float | None,
    web_weight: float | None,
) -> dict[str, object]:
    load_local_env(root)
    answer_text = answer_file.read_text(encoding="utf-8")
    signal = detect_web_gap_signal(answer_text, eval_result)
    resolved_wiki_weight = wiki_weight if wiki_weight is not None else env_float("CWIKI_WEB_WIKI_WEIGHT", DEFAULT_WIKI_WEIGHT)
    resolved_web_weight = web_weight if web_weight is not None else env_float("CWIKI_WEB_WEIGHT", DEFAULT_WEB_WEIGHT)
    resolved_max_sources = max_web_sources if max_web_sources is not None else env_int("CWIKI_WEB_MAX_SOURCES", 6)
    env_web_enabled = env_bool("CWIKI_WEB_ENABLED", True)
    web_enabled = env_web_enabled and resolved_web_weight > 0 and resolved_max_sources > 0
    result: dict[str, object] = {
        "enabled": True,
        "triggered": bool(signal["triggered"]),
        "status": "created" if signal["triggered"] else "not_triggered",
        "reason": signal["summary"],
        "categories": signal["categories"],
        "matched_excerpts": signal["matched_excerpts"],
        "wiki_weight": resolved_wiki_weight,
        "web_weight": resolved_web_weight,
        "web_mode": "enabled" if web_enabled else "disabled",
        "max_web_sources": resolved_max_sources,
        "answer_file": display_path(answer_file, root),
    }
    if not signal["triggered"]:
        return result

    question = str(eval_result.get("question") or extract_question_from_answer(answer_text, parse_frontmatter(answer_text)) or answer_file.stem)
    focus = render_web_gap_focus(question, signal, answer_file, root)
    prompt_file, brief_file, research_file, fusion_prompt_file, _hits, _prompt, _brief = create_web_query_prompt(
        root.as_posix(),
        question,
        top_k,
        resolved_max_sources,
        resolved_wiki_weight,
        resolved_web_weight,
        web_enabled,
        focus,
    )
    report_file = write_web_gap_followup_report(
        root,
        question,
        answer_file,
        signal,
        prompt_file,
        brief_file,
        research_file,
        fusion_prompt_file,
        resolved_wiki_weight,
        resolved_web_weight,
        resolved_max_sources,
    )
    result.update(
        {
            "web_query_prompt": display_path(prompt_file, root),
            "web_brief": display_path(brief_file, root),
            "web_research_file": display_path(research_file, root),
            "fusion_prompt": display_path(fusion_prompt_file, root),
            "followup_report": display_path(report_file, root),
        }
    )
    return result


def detect_web_gap_signal(answer_text: str, eval_result: dict[str, object] | None = None) -> dict[str, object]:
    eval_result = eval_result or {}
    language = str(eval_result.get("language", "en"))
    body = markdown_body(answer_text)
    answer_body = extract_answer_body(body)
    gap_text = "\n".join(
        section
        for section in (
            extract_markdown_section(answer_body, "Gaps"),
            extract_markdown_section(answer_body, "缺口"),
            extract_markdown_section(answer_body, "Limitations"),
            extract_markdown_section(answer_body, "限制"),
            extract_markdown_section(answer_body, "Open Questions"),
            extract_markdown_section(answer_body, "开放问题"),
        )
        if section
    )
    llm = eval_result.get("llm_assisted")
    llm_response = str(llm.get("response", "")) if isinstance(llm, dict) else ""
    warning_text = "\n".join(str(item.get("message", "")) for item in eval_result.get("warnings", []) if isinstance(item, dict))
    search_text = "\n\n".join(part for part in (gap_text, llm_response, warning_text) if part).strip()

    categories: list[dict[str, str]] = []
    excerpts: list[str] = []
    for key, pattern, zh_reason, en_reason in WEB_GAP_PATTERNS:
        if re.search(pattern, search_text, flags=re.IGNORECASE):
            categories.append({"key": key, "reason": zh_reason if language == "zh-CN" or contains_chinese(search_text) else en_reason})
            excerpts.extend(matching_gap_lines(search_text, pattern))
    seen: set[str] = set()
    unique_excerpts: list[str] = []
    for item in excerpts:
        if item not in seen:
            unique_excerpts.append(item)
            seen.add(item)
    summary = "；".join(item["reason"] for item in categories) if categories else "未发现需要联网补证的 gap"
    return {
        "triggered": bool(categories),
        "summary": summary,
        "categories": categories,
        "matched_excerpts": unique_excerpts[:8],
    }


def matching_gap_lines(text: str, pattern: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or not re.search(pattern, line, flags=re.IGNORECASE):
            continue
        lines.append(line[:240])
    if lines:
        return lines
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return []
    start = max(0, match.start() - 80)
    end = min(len(text), match.end() + 160)
    return [re.sub(r"\s+", " ", text[start:end]).strip()]


def render_web_gap_focus(question: str, signal: dict[str, object], answer_file: Path, root: Path) -> str:
    reasons = signal.get("categories") if isinstance(signal.get("categories"), list) else []
    reason_lines = "\n".join(f"- {item.get('reason')}" for item in reasons if isinstance(item, dict)) or "- 补齐答案中的外部证据缺口。"
    excerpts = signal.get("matched_excerpts") if isinstance(signal.get("matched_excerpts"), list) else []
    excerpt_lines = "\n".join(f"- {item}" for item in excerpts) or "- No matched gap excerpt recorded."
    return f"""This web follow-up was triggered by answer/evaluation gaps.

Original question: {question}
Answer file: `{display_path(answer_file, root)}`

Research goals:
{reason_lines}

Matched gap excerpts:
{excerpt_lines}

Browser research should prioritize primary or durable sources, collect concrete evidence for these gaps, and then use the fusion prompt to produce an updated answer that separates local wiki evidence from web evidence."""


def write_web_gap_followup_report(
    root: Path,
    question: str,
    answer_file: Path,
    signal: dict[str, object],
    prompt_file: Path,
    brief_file: Path,
    research_file: Path,
    fusion_prompt_file: Path,
    wiki_weight: float,
    web_weight: float,
    max_web_sources: int,
) -> Path:
    ensure_dir(root / ".cwiki" / "web-gaps")
    path = root / ".cwiki" / "web-gaps" / f"web-gap-{timestamp()}-{slugify(question)}.md"
    categories = signal.get("categories") if isinstance(signal.get("categories"), list) else []
    category_lines = "\n".join(f"- {item.get('reason')}" for item in categories if isinstance(item, dict)) or "- None"
    excerpts = signal.get("matched_excerpts") if isinstance(signal.get("matched_excerpts"), list) else []
    excerpt_lines = "\n".join(f"- {item}" for item in excerpts) or "- None"
    path.write_text(
        f"""---
title: Web Gap Follow-up - {question}
tags: [web-gap, follow-up]
updated: {today()}
status: pending
wiki_weight: {wiki_weight}
web_weight: {web_weight}
max_web_sources: {max_web_sources}
---

# Web Gap Follow-up - {question}

## Why This Was Created

The answer or its evaluation contained gaps that require current or external evidence.

## Trigger Categories

{category_lines}

## Matched Gap Excerpts

{excerpt_lines}

## Artifacts

- Answer file: `{display_path(answer_file, root)}`
- Web query prompt: `{display_path(prompt_file, root)}`
- Web brief: `{display_path(brief_file, root)}`
- Web research workspace: `{display_path(research_file, root)}`
- Evidence fusion prompt: `{display_path(fusion_prompt_file, root)}`

## Next Step

Give the web query prompt to a browser-capable agent using `wiki-agent-browser`. After it fills the web research workspace, use the fusion prompt to produce the updated final answer.
""",
        encoding="utf-8",
    )
    return path


def render_web_followup_cli_summary(root: Path, followup: dict[str, object]) -> str:
    if not followup.get("triggered"):
        return "\nWeb gap follow-up: not triggered."
    return (
        "\nWeb gap follow-up: created\n"
        f"- Reason: {followup.get('reason')}\n"
        f"- Web mode: {followup.get('web_mode', '-')}\n"
        f"- Web query prompt: {followup.get('web_query_prompt')}\n"
        f"- Web research workspace: {followup.get('web_research_file')}\n"
        f"- Evidence fusion prompt: {followup.get('fusion_prompt')}\n"
        f"- Follow-up report: {followup.get('followup_report')}"
    )


def answer_wiki(
    target: str,
    question: str,
    top_k: int,
    retrieval: str,
    graph_rerank: bool,
    provider: str,
    model: str | None,
    api_key_env: str | None,
    base_url: str | None,
    max_output_tokens: int,
    graph_rerank_output_tokens: int,
    web_on_gaps: bool = False,
    web_gap_top_k: int = DEFAULT_TOP_K,
    web_gap_max_sources: int | None = None,
    web_gap_wiki_weight: float | None = None,
    web_gap_web_weight: float | None = None,
) -> int:
    root = Path(target).resolve()
    load_local_env(root)
    provider = (provider or os.environ.get("CWIKI_PROVIDER") or "openai").lower()
    model = resolve_model(provider, model)
    api_key_env = resolve_api_key_env(provider, api_key_env)
    base_url = resolve_base_url(provider, base_url)

    if provider not in {"openai", "glm"}:
        raise RuntimeError(f"Unsupported provider: {provider}. Currently supported: openai, glm")

    prompt_file, brief_file, hits, prompt, _brief = create_query_prompt(
        target,
        question,
        top_k,
        retrieval,
        graph_rerank,
        provider,
        model,
        api_key_env,
        base_url,
        graph_rerank_output_tokens,
    )
    api_key = os.environ.get(api_key_env)
    if not api_key:
        print(f"Created query prompt: {prompt_file.relative_to(root).as_posix()}")
        print(f"Created human brief: {brief_file.relative_to(root).as_posix()}")
        raise RuntimeError(f"Missing API key. Set {api_key_env}=... or use `cwiki ask` for context-only mode.")

    instructions = (
        "You answer questions against a local LLM Compound Wiki. "
        "Use this structure exactly: `## Evidence Used`, `## Answer`, `## Gaps`. "
        "In `## Evidence Used`, list every Relevant Page. For each page, write either `- [[slug]] - used - source: raw/...` or `- [[slug]] - not used - reason: ...`. "
        "Use only the provided wiki context. In the answer body, cite every wiki page you use as [[slug]]. "
        "For factual claims, include nearby source paths or URLs from Claim Ledger rows, such as raw/... or .cwiki/web-research/.... "
        "Use the Relevant Pages that materially support the answer; if one is not useful, mention that in a Gaps section. "
        "Always include a `## Gaps` section that states missing evidence, weak coverage, limitations, or that no gaps are known. "
        "Do not invent facts outside the context pack."
    )
    if provider == "openai":
        llm_response = call_openai_responses(api_key, model, instructions, prompt, max_output_tokens)
    else:
        llm_response = call_openai_compatible_chat(
            api_key=api_key,
            base_url=base_url,
            provider_name="GLM",
            model=model,
            instructions=instructions,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
        )
    answer = llm_response.text
    health_warnings = answer_health_warnings(answer)
    answer_file = write_answer_file(root, question, answer, prompt_file, hits, provider, model, health_warnings, llm_response.usage, llm_response.cost)
    record_llm_usage(
        root,
        "answer",
        provider,
        model,
        llm_response,
        artifact=answer_file.as_posix(),
        question=question,
        prompt_file=prompt_file.as_posix(),
        status="suspicious" if health_warnings else "completed",
        metadata={"retrieval": retrieval, "graph_rerank": graph_rerank},
    )

    print(answer)
    print(f"\nSaved answer: {answer_file.relative_to(root).as_posix()}")
    print(f"Query prompt: {prompt_file.relative_to(root).as_posix()}")
    print(llm_usage_line(llm_response.usage, llm_response.cost))
    if web_on_gaps:
        pages = collect_pages(root)
        eval_result = build_answer_eval(root, answer_file, pages)
        web_followup = create_web_followup_for_answer_gaps(
            root,
            answer_file,
            eval_result,
            web_gap_top_k,
            web_gap_max_sources,
            web_gap_wiki_weight,
            web_gap_web_weight,
        )
        print(render_web_followup_cli_summary(root, web_followup))
    if health_warnings:
        print("\nAnswer may be truncated; please retry.", file=sys.stderr)
        for item in health_warnings:
            print(f"- {item}", file=sys.stderr)
        print(f"Saved suspicious answer for inspection: {answer_file.relative_to(root).as_posix()}", file=sys.stderr)
        return 2
    return 0


def resolve_model(provider: str, model: str | None) -> str:
    if model:
        return model
    if provider == "glm":
        return os.environ.get("CWIKI_GLM_MODEL") or os.environ.get("CWIKI_MODEL") or DEFAULT_GLM_MODEL
    return os.environ.get("CWIKI_OPENAI_MODEL") or os.environ.get("CWIKI_MODEL") or DEFAULT_OPENAI_MODEL


def answer_health_warnings(answer: str) -> list[str]:
    warnings: list[str] = []
    if has_unclosed_wikilink(answer):
        warnings.append("Unclosed wikilink detected.")
    sections = markdown_headings(answer)
    if "Answer" not in sections:
        warnings.append("Missing required `## Answer` section.")
    if "Gaps" not in sections:
        warnings.append("Missing required `## Gaps` section.")
    body = extract_answer_body(answer)
    if not body or len(strip_evaluation_scaffolding(body)) < 40:
        warnings.append("Answer body is too short after removing scaffolding.")
    return warnings


def resolve_api_key_env(provider: str, api_key_env: str | None) -> str:
    if api_key_env:
        return api_key_env
    if provider == "glm":
        return os.environ.get("CWIKI_GLM_API_KEY_ENV") or "GLM_API_KEY"
    return os.environ.get("CWIKI_OPENAI_API_KEY_ENV") or "OPENAI_API_KEY"


def resolve_base_url(provider: str, base_url: str | None) -> str:
    if base_url:
        return base_url.rstrip("/")
    if provider == "glm":
        return (os.environ.get("GLM_BASE_URL") or DEFAULT_GLM_BASE_URL).rstrip("/")
    return "https://api.openai.com/v1"


def call_openai_responses(api_key: str, model: str, instructions: str, prompt: str, max_output_tokens: int) -> LLMResponse:
    payload = {
        "model": model,
        "instructions": instructions,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
    }
    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error ({error.code}): {body}") from error
    except urlerror.URLError as error:
        raise RuntimeError(f"OpenAI API request failed: {error}") from error

    text = extract_response_text(data)
    if not text:
        raise RuntimeError("OpenAI API returned no text output.")
    usage = llm_usage_from_response("openai", model, data)
    return LLMResponse(text, usage, estimate_llm_cost("openai", model, usage))


def call_openai_compatible_chat(
    api_key: str,
    base_url: str,
    provider_name: str,
    model: str,
    instructions: str,
    prompt: str,
    max_output_tokens: int,
    extra_payload: dict[str, object] | None = None,
) -> LLMResponse:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_output_tokens,
    }
    if extra_payload:
        payload.update(extra_payload)
    url = f"{base_url.rstrip('/')}/chat/completions"
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{provider_name} API error ({error.code}): {body}") from error
    except urlerror.URLError as error:
        raise RuntimeError(f"{provider_name} API request failed: {error}") from error

    text = extract_chat_completion_text(data)
    if not text:
        raise RuntimeError(f"{provider_name} API returned no text output. {chat_completion_shape_hint(data)}")
    provider = provider_name.lower()
    usage = llm_usage_from_response(provider, model, data)
    return LLMResponse(text, usage, estimate_llm_cost(provider, model, usage))


def append_chat_content(chunks: list[str], value: object) -> None:
    if isinstance(value, str):
        if value.strip():
            chunks.append(value)
        return
    if isinstance(value, dict):
        for key in ("text", "content", "value"):
            nested = value.get(key)
            if isinstance(nested, (str, dict, list)):
                append_chat_content(chunks, nested)
        return
    if isinstance(value, list):
        for item in value:
            append_chat_content(chunks, item)


def extract_chat_completion_text(data: dict[str, object]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list):
        return ""
    chunks: list[str] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        append_chat_content(chunks, choice.get("text"))
        message = choice.get("message")
        if isinstance(message, dict):
            for key in ("content", "reasoning_content", "reasoning", "text"):
                append_chat_content(chunks, message.get(key))
        delta = choice.get("delta")
        if isinstance(delta, dict):
            for key in ("content", "reasoning_content", "text"):
                append_chat_content(chunks, delta.get(key))
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def chat_completion_shape_hint(data: dict[str, object]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return f"Response keys: {', '.join(sorted(str(key) for key in data.keys())) or 'none'}."
    first = choices[0]
    if not isinstance(first, dict):
        return "First choice was not an object."
    message = first.get("message")
    message_keys = sorted(str(key) for key in message.keys()) if isinstance(message, dict) else []
    return (
        f"Response keys: {', '.join(sorted(str(key) for key in data.keys())) or 'none'}; "
        f"choice keys: {', '.join(sorted(str(key) for key in first.keys())) or 'none'}; "
        f"message keys: {', '.join(message_keys) or 'none'}."
    )


def extract_response_text(data: dict[str, object]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def write_answer_file(
    root: Path,
    question: str,
    answer: str,
    prompt_file: Path,
    hits: list[tuple[Page, int]],
    provider: str,
    model: str,
    health_warnings: list[str] | None = None,
    usage: dict[str, object] | None = None,
    cost: dict[str, object] | None = None,
) -> Path:
    date = today()
    slug = slugify(question)
    answers_dir = root / ".cwiki" / "answers"
    ensure_dir(answers_dir)
    answer_file = answers_dir / f"answer-{timestamp()}-{slug}.md"
    relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}`" for page, score in hits) or "- No direct matches"
    health_warnings = health_warnings or []
    health_status = "failed" if health_warnings else "passed"
    status = "suspicious" if health_warnings else "draft"
    health_frontmatter = "\n".join(f"  - {yaml_quote(item)}" for item in health_warnings) or "  []"
    health_section = ""
    if health_warnings:
        warning_lines = "\n".join(f"- {item}" for item in health_warnings)
        health_section = f"""
## Answer Health

Status: suspicious

This answer may be truncated or malformed. Please retry before using it as a final answer.

{warning_lines}

"""
    answer_file.write_text(
        f"""---
title: Answer - {question}
tags: [answer]
sources: {len(hits)}
updated: {date}
status: {status}
provider: {provider}
model: {model}
{llm_usage_frontmatter(usage, cost)}
answer_health: {health_status}
health_warnings:
{health_frontmatter}
---

# Answer - {question}

{health_section}## Question

{question}

## Answer

{answer}

## Relevant Pages

{relevant_pages}

## LLM Usage

{llm_usage_bullets(usage, cost)}

## Query Prompt

`{prompt_file.relative_to(root).as_posix()}`
""",
        encoding="utf-8",
    )
    return answer_file


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def infer_title(source: str) -> str:
    if re.match(r"^https?://", source, flags=re.IGNORECASE):
        parsed = urlparse(source)
        last = next((part for part in reversed(parsed.path.split("/")) if part), parsed.hostname or "untitled")
        return re.sub(r"\.[A-Za-z0-9]+$", "", last).replace("-", " ").replace("_", " ")
    return Path(source).stem.replace("-", " ").replace("_", " ")


def read_source_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in {"", ".txt", ".md", ".markdown", ".csv", ".json", ".yaml", ".yml"}:
        return path.read_text(encoding="utf-8"), "text"
    if suffix == ".docx":
        return extract_docx_text(path), "docx"
    if suffix == ".pptx":
        return extract_pptx_text(path), "pptx"
    if suffix == ".xlsx":
        return extract_xlsx_text(path), "xlsx"
    if suffix == ".pdf":
        return extract_pdf_text(path), "pdf"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
        return image_reference_text(path), "image"
    try:
        return path.read_text(encoding="utf-8"), "text"
    except UnicodeDecodeError as error:
        raise RuntimeError(
            f"Unsupported or non-UTF-8 source file: {path}. "
            "Convert it to UTF-8 text first, or use a supported .txt, .md, .docx, or text-extractable .pdf file."
        ) from error


def extract_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except KeyError as error:
        raise RuntimeError(f"Invalid .docx file, missing word/document.xml: {path}") from error
    except zipfile.BadZipFile as error:
        raise RuntimeError(f"Invalid .docx file: {path}") from error

    root = ElementTree.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{{{namespace['w']}}}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{{{namespace['w']}}}tab":
                parts.append("\t")
            elif node.tag == f"{{{namespace['w']}}}br":
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    extracted = "\n\n".join(paragraphs).strip()
    if not extracted:
        raise RuntimeError(f"No text could be extracted from .docx file: {path}")
    return extracted


def sorted_ooxml_parts(names: list[str], prefix: str, suffix: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+){re.escape(suffix)}$")
    matched = []
    for name in names:
        match = pattern.match(name)
        if match:
            matched.append((int(match.group(1)), name))
    return [name for _, name in sorted(matched)]


def extract_xml_text(xml: bytes) -> str:
    root = ElementTree.fromstring(xml)
    chunks: list[str] = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            chunks.append(node.text)
    return " ".join(chunks).strip()


def extract_pptx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            slide_parts = sorted_ooxml_parts(names, "ppt/slides/slide", ".xml")
            if not slide_parts:
                raise RuntimeError(f"No slides found in .pptx file: {path}")
            sections: list[str] = []
            for index, part in enumerate(slide_parts, start=1):
                text = extract_xml_text(archive.read(part))
                if text:
                    sections.append(f"## Slide {index}\n\n{text}")
                else:
                    sections.append(f"## Slide {index}\n\n[No extractable text]")
    except zipfile.BadZipFile as error:
        raise RuntimeError(f"Invalid .pptx file: {path}") from error
    extracted = "\n\n".join(sections).strip()
    if not extracted:
        raise RuntimeError(f"No text could be extracted from .pptx file: {path}")
    return extracted


def extract_xlsx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            shared_strings = read_xlsx_shared_strings(archive)
            sheet_parts = sorted_ooxml_parts(names, "xl/worksheets/sheet", ".xml")
            if not sheet_parts:
                raise RuntimeError(f"No worksheets found in .xlsx file: {path}")
            sections = [extract_xlsx_sheet(archive.read(part), shared_strings, index) for index, part in enumerate(sheet_parts, start=1)]
    except zipfile.BadZipFile as error:
        raise RuntimeError(f"Invalid .xlsx file: {path}") from error
    extracted = "\n\n".join(section for section in sections if section.strip()).strip()
    if not extracted:
        raise RuntimeError(f"No text could be extracted from .xlsx file: {path}")
    return extracted


def read_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root:
        parts = [node.text or "" for node in item.iter() if node.tag.endswith("}t")]
        strings.append("".join(parts))
    return strings


def extract_xlsx_sheet(xml: bytes, shared_strings: list[str], index: int) -> str:
    root = ElementTree.fromstring(xml)
    rows: list[str] = []
    for row in root.iter():
        if not row.tag.endswith("}row"):
            continue
        cells: list[str] = []
        for cell in row:
            if not cell.tag.endswith("}c"):
                continue
            cell_type = cell.attrib.get("t")
            value_node = next((child for child in cell if child.tag.endswith("}v")), None)
            inline_text = " ".join(node.text or "" for node in cell.iter() if node.tag.endswith("}t")).strip()
            value = ""
            if inline_text:
                value = inline_text
            elif value_node is not None and value_node.text is not None:
                raw = value_node.text
                if cell_type == "s" and raw.isdigit() and int(raw) < len(shared_strings):
                    value = shared_strings[int(raw)]
                else:
                    value = raw
            cells.append(value)
        if any(cells):
            rows.append(" | ".join(cells))
    body = "\n".join(rows).strip() or "[No extractable cell text]"
    return f"## Sheet {index}\n\n{body}"


def image_reference_text(path: Path) -> str:
    return f"""Image source: {path}

This raw record references an image file. Use the built-in `wiki-parse-image` skill to inspect the image, extract visible text, describe diagrams/charts/UI, and record uncertainty before compiling claims into `wiki/`.
"""


def extract_pdf_text(path: Path) -> str:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise RuntimeError(
            "PDF capture requires the `pdftotext` command on PATH. "
            "Install poppler or convert the PDF to UTF-8 text, then run `cwiki capture` on the extracted text file."
        )
    result = subprocess.run(
        [pdftotext, "-layout", str(path), "-"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"PDF text extraction failed for {path}: {result.stderr.strip() or 'unknown error'}")
    text = result.stdout.strip()
    if not text:
        raise RuntimeError(f"No text could be extracted from PDF file: {path}")
    return text


def capture_source(target: str, source: str, title: str | None) -> None:
    root = Path(target).resolve()
    assert_wiki(root)
    source_title = title or infer_title(source)
    slug = slugify(source_title)
    date = today()
    is_url = re.match(r"^https?://", source, flags=re.IGNORECASE) is not None
    raw_dir = root / "raw" / "captures"
    ensure_dir(raw_dir)
    raw_file = raw_dir / f"{date}-{slug}.md"

    if is_url:
        body = f"""---
title: {source_title}
source: {source}
captured: {date}
type: url
---

# {source_title}

Source URL: {source}

Agent instruction: fetch this URL, read it in full, and compile it into the wiki using WIKI_SCHEMA.md.
"""
    else:
        absolute = Path(source).resolve()
        if not absolute.is_file():
            raise RuntimeError(f"Not a file: {absolute}")
        text, source_type = read_source_text(absolute)
        body = f"""---
title: {source_title}
source: {absolute}
captured: {date}
type: {source_type}
---

# {source_title}

Original file: {absolute}

## Content

{text}
"""

    raw_file.write_text(body, encoding="utf-8")
    prompt_file = root / ".cwiki" / "prompts" / f"ingest-{date}-{slug}.md"
    prompt_file.write_text(
        f"""---
title: Ingest Prompt - {source_title}
tags: [ingest, prompt]
sources: 1
updated: {date}
status: pending
---

# Ingest Prompt - {source_title}

Read `{raw_file.relative_to(root).as_posix()}` in full and compile it into this wiki.

Follow `WIKI_SCHEMA.md`:

1. Read `wiki/index.md`.
2. Preserve the source language. If the source is Chinese, write Chinese wiki pages; if it is English, write English wiki pages. Do not translate by default.
3. Identify existing summaries, entities, concepts, comparisons, overview, or synthesis pages to update.
4. Mandatory global pages refresh:
   - Open both `wiki/overview.md` and `wiki/synthesis.md` on every ingest.
   - Update `overview.md` with the current map, scope, important page clusters, entry links, and open navigation questions.
   - Update `synthesis.md` with the current thesis state, stable claims, contradictions, evidence inventory, or a clear note that no thesis is promoted yet and why.
   - If either page still has `status: seed`, replace seed guidance with real wiki-specific content once this wiki contains real ingested knowledge.
5. Extract source-backed claims into claim ledgers.
6. Add bidirectional wikilinks where appropriate.
7. Run `cwiki index .`.
8. Append to `wiki/log.md`.
9. If the agent platform exposes token or cost numbers for this ingest, record them with `cwiki usage-log . --operation ingest --provider agent-platform --model <visible-model-name> ...`.

Final note must include:

- Pages created
- Pages updated
- What changed in `wiki/overview.md`
- What changed in `wiki/synthesis.md`
- Whether platform-model usage was recorded or unavailable
""",
        encoding="utf-8",
    )

    print(f"Captured source: {raw_file.relative_to(root).as_posix()}")
    print(f"Created ingest prompt: {prompt_file.relative_to(root).as_posix()}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cwiki",
        description="LLM Compound Wiki",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  cwiki init ./my-wiki --domain "AI research notes"
  cwiki capture . https://example.com/article --title "Example Article"
  cwiki ask . "What does this wiki know about retrieval?"
  cwiki web-ask . "What changed recently about this topic?" --wiki-weight 0.6 --web-weight 0.4
  cwiki answer . "What does this wiki know about retrieval?" --provider glm --model glm-4.6v
  cwiki eval .
  cwiki eval-answer . .cwiki/answers/answer-example.md
  cwiki eval-all . --json
  cwiki eval-schedule . --every-days 7 --llm
  cwiki usage-report .
  cwiki usage-log . --operation ingest --provider agent-platform --model current-agent-model --input-tokens 1000 --output-tokens 500
  cwiki graph-report .
  cwiki path . retrieval synthesis
  cwiki search . "retrieval"
  cwiki lint .
""",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize a wiki")
    init_parser.add_argument("dir")
    init_parser.add_argument("--domain")

    index_parser = subparsers.add_parser("index", help="Regenerate wiki/index.md")
    index_parser.add_argument("dir")

    lint_parser = subparsers.add_parser("lint", help="Check wiki health")
    lint_parser.add_argument("dir")

    eval_parser = subparsers.add_parser("eval", help="Evaluate wiki quality")
    eval_parser.add_argument("dir")
    eval_parser.add_argument("--output")
    eval_parser.add_argument("--no-write", action="store_true")
    eval_parser.add_argument("--json", action="store_true")
    eval_parser.add_argument("--llm", action="store_true")
    eval_parser.add_argument("--provider", default=None)
    eval_parser.add_argument("--model", default=None)
    eval_parser.add_argument("--api-key-env", default=None)
    eval_parser.add_argument("--base-url", default=None)
    eval_parser.add_argument("--max-output-tokens", type=int, default=1000)
    eval_parser.add_argument("--agent-eval-file", default=None, help="Attach a Markdown LLM-assisted evaluation written by the current agent platform")
    eval_parser.add_argument("--agent-model", default=None, help="Model label to record for --agent-eval-file")

    eval_answer_parser = subparsers.add_parser("eval-answer", help="Evaluate answer quality")
    eval_answer_parser.add_argument("dir")
    eval_answer_parser.add_argument("answer_file")
    eval_answer_parser.add_argument("--output")
    eval_answer_parser.add_argument("--no-write", action="store_true")
    eval_answer_parser.add_argument("--json", action="store_true")
    eval_answer_parser.add_argument("--llm", action="store_true")
    eval_answer_parser.add_argument("--provider", default=None)
    eval_answer_parser.add_argument("--model", default=None)
    eval_answer_parser.add_argument("--api-key-env", default=None)
    eval_answer_parser.add_argument("--base-url", default=None)
    eval_answer_parser.add_argument("--max-output-tokens", type=int, default=1000)
    eval_answer_parser.add_argument("--agent-eval-file", default=None, help="Attach a Markdown LLM-assisted evaluation written by the current agent platform")
    eval_answer_parser.add_argument("--agent-model", default=None, help="Model label to record for --agent-eval-file")
    eval_answer_parser.add_argument("--web-on-gaps", action="store_true", help="Create web-ask/fusion artifacts when answer gaps need external evidence")
    eval_answer_parser.add_argument("--web-gap-top-k", type=int, default=DEFAULT_TOP_K, help="Local wiki pages to include in web gap follow-up prompts")
    eval_answer_parser.add_argument("--web-gap-max-sources", type=int, default=None, help="Override max web sources for web gap follow-up")
    eval_answer_parser.add_argument("--web-gap-wiki-weight", type=float, default=None, help="Override local wiki evidence weight for web gap follow-up")
    eval_answer_parser.add_argument("--web-gap-web-weight", type=float, default=None, help="Override web evidence weight for web gap follow-up")

    eval_all_parser = subparsers.add_parser("eval-all", help="Evaluate wiki quality and optional answer quality")
    eval_all_parser.add_argument("dir")
    eval_all_parser.add_argument("--answer")
    eval_all_parser.add_argument("--output")
    eval_all_parser.add_argument("--no-write", action="store_true")
    eval_all_parser.add_argument("--json", action="store_true")
    eval_all_parser.add_argument("--wiki-only", action="store_true")
    eval_all_parser.add_argument("--llm", action="store_true")
    eval_all_parser.add_argument("--provider", default=None)
    eval_all_parser.add_argument("--model", default=None)
    eval_all_parser.add_argument("--api-key-env", default=None)
    eval_all_parser.add_argument("--base-url", default=None)
    eval_all_parser.add_argument("--max-output-tokens", type=int, default=1000)
    eval_all_parser.add_argument("--agent-eval-file", default=None, help="Attach a Markdown LLM-assisted evaluation written by the current agent platform")
    eval_all_parser.add_argument("--agent-model", default=None, help="Model label to record for --agent-eval-file")

    eval_schedule_parser = subparsers.add_parser("eval-schedule", help="Configure or run scheduled combined evaluation")
    eval_schedule_parser.add_argument("dir")
    eval_schedule_parser.add_argument("--every-days", type=int, default=None)
    eval_schedule_parser.add_argument("--disable", action="store_true")
    eval_schedule_parser.add_argument("--run-if-due", action="store_true")
    eval_schedule_parser.add_argument("--answer")
    eval_schedule_parser.add_argument("--wiki-only", action="store_true")
    eval_schedule_parser.add_argument("--json", action="store_true")
    eval_schedule_parser.add_argument("--llm", action="store_true")
    eval_schedule_parser.add_argument("--provider", default=None)
    eval_schedule_parser.add_argument("--model", default=None)
    eval_schedule_parser.add_argument("--api-key-env", default=None)
    eval_schedule_parser.add_argument("--base-url", default=None)
    eval_schedule_parser.add_argument("--max-output-tokens", type=int, default=1000)

    graph_parser = subparsers.add_parser("graph", help="Generate .cwiki/graph/graph.json from wiki links")
    graph_parser.add_argument("dir")

    graph_report_parser = subparsers.add_parser("graph-report", help="Generate graph.json and graph.md")
    graph_report_parser.add_argument("dir")

    path_parser = subparsers.add_parser("path", help="Find the shortest wikilink path between two wiki pages")
    path_parser.add_argument("dir")
    path_parser.add_argument("source")
    path_parser.add_argument("target")

    explain_parser = subparsers.add_parser("explain", help="Explain one wiki page as a graph node")
    explain_parser.add_argument("dir")
    explain_parser.add_argument("slug")

    search_parser = subparsers.add_parser("search", help="Search wiki pages")
    search_parser.add_argument("dir")
    search_parser.add_argument("query", nargs="+")

    usage_report_parser = subparsers.add_parser("usage-report", help="Report LLM token usage and estimated cost")
    usage_report_parser.add_argument("dir")
    usage_report_parser.add_argument("--operation", default=None)
    usage_report_parser.add_argument("--artifact", default=None, help="Filter by answer, prompt, eval, or other artifact path substring")
    usage_report_parser.add_argument("--question", default=None, help="Filter by question substring")
    usage_report_parser.add_argument("--provider", default=None)
    usage_report_parser.add_argument("--model", default=None)
    usage_report_parser.add_argument("--since", default=None, help="ISO date/time lower bound, for example 2026-05-18 or 2026-05-18T10:00:00")
    usage_report_parser.add_argument("--until", default=None, help="ISO date/time upper bound")
    usage_report_parser.add_argument("--json", action="store_true")

    usage_log_parser = subparsers.add_parser("usage-log", help="Manually record external or agent-platform LLM usage")
    usage_log_parser.add_argument("dir")
    usage_log_parser.add_argument("--operation", required=True, help="Workflow step, for example ingest, update, answer, eval, web-research")
    usage_log_parser.add_argument("--provider", default="agent-platform")
    usage_log_parser.add_argument("--model", default="current-agent-model")
    usage_log_parser.add_argument("--input-tokens", type=int, default=None)
    usage_log_parser.add_argument("--output-tokens", type=int, default=None)
    usage_log_parser.add_argument("--total-tokens", type=int, default=None)
    usage_log_parser.add_argument("--estimated-cost", type=float, default=None)
    usage_log_parser.add_argument("--currency", default="USD")
    usage_log_parser.add_argument("--artifact", default=None)
    usage_log_parser.add_argument("--question", default=None)
    usage_log_parser.add_argument("--status", default="completed")
    usage_log_parser.add_argument("--metadata-json", default=None)

    ask_parser = subparsers.add_parser("ask", help="Create a query prompt from wiki context")
    ask_parser.add_argument("dir")
    ask_parser.add_argument("question", nargs="+")
    ask_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ask_parser.add_argument("--retrieval", choices=sorted(RETRIEVAL_MODES), default="auto")
    ask_parser.add_argument("--graph-rerank", action="store_true", help="Use the configured model to rerank graph/path/synthesis retrieval candidates")
    ask_parser.add_argument("--provider", default=None, help="Provider for --graph-rerank")
    ask_parser.add_argument("--model", default=None, help="Model for --graph-rerank")
    ask_parser.add_argument("--api-key-env", default=None, help="API key env var for --graph-rerank")
    ask_parser.add_argument("--base-url", default=None, help="Base URL for --graph-rerank")
    ask_parser.add_argument("--graph-rerank-output-tokens", type=int, default=500)
    ask_parser.add_argument("--show-context", action="store_true")

    web_ask_parser = subparsers.add_parser(
        "web-ask",
        help="Create a browser-agent prompt that combines local wiki context with web research",
    )
    web_ask_parser.add_argument("dir")
    web_ask_parser.add_argument("question", nargs="+")
    web_ask_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    web_ask_parser.add_argument("--max-web-sources", type=int, default=None)
    web_ask_parser.add_argument("--wiki-weight", type=float, default=None)
    web_ask_parser.add_argument("--web-weight", type=float, default=None)
    web_ask_parser.add_argument("--no-web", action="store_true")
    web_ask_parser.add_argument("--show-context", action="store_true")

    answer_parser = subparsers.add_parser("answer", help="Answer a question using a model and wiki context")
    answer_parser.add_argument("dir")
    answer_parser.add_argument("question", nargs="+")
    answer_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    answer_parser.add_argument("--retrieval", choices=sorted(RETRIEVAL_MODES), default="auto")
    answer_parser.add_argument("--graph-rerank", action="store_true", help="Use the configured model to rerank graph/path/synthesis retrieval candidates before answering")
    answer_parser.add_argument("--provider", default=None)
    answer_parser.add_argument("--model", default=None)
    answer_parser.add_argument("--api-key-env", default=None)
    answer_parser.add_argument("--base-url", default=None)
    answer_parser.add_argument("--max-output-tokens", type=int, default=1200)
    answer_parser.add_argument("--graph-rerank-output-tokens", type=int, default=500)
    answer_parser.add_argument("--web-on-gaps", action="store_true", help="After answering, create web-ask/fusion artifacts when gaps need external evidence")
    answer_parser.add_argument("--web-gap-top-k", type=int, default=DEFAULT_TOP_K, help="Local wiki pages to include in web gap follow-up prompts")
    answer_parser.add_argument("--web-gap-max-sources", type=int, default=None, help="Override max web sources for web gap follow-up")
    answer_parser.add_argument("--web-gap-wiki-weight", type=float, default=None, help="Override local wiki evidence weight for web gap follow-up")
    answer_parser.add_argument("--web-gap-web-weight", type=float, default=None, help="Override web evidence weight for web gap follow-up")

    capture_parser = subparsers.add_parser("capture", help="Capture a source and create an ingest prompt")
    capture_parser.add_argument("dir")
    capture_parser.add_argument("source")
    capture_parser.add_argument("--title")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "init":
            init_wiki(args.dir, args.domain)
        elif args.command == "index":
            index_wiki(args.dir)
        elif args.command == "lint":
            return lint_wiki(args.dir)
        elif args.command == "eval":
            eval_wiki(args.dir, args.output, args.no_write, args.json, args.llm, args.provider, args.model, args.api_key_env, args.base_url, args.max_output_tokens, args.agent_eval_file, args.agent_model)
        elif args.command == "eval-answer":
            eval_answer(
                args.dir,
                args.answer_file,
                args.output,
                args.no_write,
                args.json,
                args.llm,
                args.provider,
                args.model,
                args.api_key_env,
                args.base_url,
                args.max_output_tokens,
                args.agent_eval_file,
                args.agent_model,
                args.web_on_gaps,
                args.web_gap_top_k,
                args.web_gap_max_sources,
                args.web_gap_wiki_weight,
                args.web_gap_web_weight,
            )
        elif args.command == "eval-all":
            eval_all(args.dir, args.answer, args.output, args.no_write, args.json, args.wiki_only, args.llm, args.provider, args.model, args.api_key_env, args.base_url, args.max_output_tokens, args.agent_eval_file, args.agent_model)
        elif args.command == "eval-schedule":
            configure_eval_schedule(
                args.dir,
                args.every_days,
                args.disable,
                args.run_if_due,
                args.answer,
                args.wiki_only,
                args.json,
                args.llm,
                args.provider,
                args.model,
                args.api_key_env,
                args.base_url,
                args.max_output_tokens,
            )
        elif args.command == "graph":
            graph_wiki(args.dir)
        elif args.command == "graph-report":
            graph_report_wiki(args.dir)
        elif args.command == "path":
            return path_wiki(args.dir, args.source, args.target)
        elif args.command == "explain":
            explain_wiki_node(args.dir, args.slug)
        elif args.command == "search":
            search_wiki(args.dir, " ".join(args.query))
        elif args.command == "usage-report":
            usage_report_wiki(
                args.dir,
                args.operation,
                args.artifact,
                args.question,
                args.provider,
                args.model,
                args.since,
                args.until,
                args.json,
            )
        elif args.command == "usage-log":
            manual_usage_log_wiki(
                args.dir,
                args.operation,
                args.provider,
                args.model,
                args.input_tokens,
                args.output_tokens,
                args.total_tokens,
                args.estimated_cost,
                args.currency,
                args.artifact,
                args.question,
                args.status,
                args.metadata_json,
            )
        elif args.command == "ask":
            ask_wiki(
                args.dir,
                " ".join(args.question),
                args.top_k,
                args.show_context,
                args.retrieval,
                args.graph_rerank,
                args.provider,
                args.model,
                args.api_key_env,
                args.base_url,
                args.graph_rerank_output_tokens,
            )
        elif args.command == "web-ask":
            web_ask_wiki(
                args.dir,
                " ".join(args.question),
                args.top_k,
                args.max_web_sources,
                args.wiki_weight,
                args.web_weight,
                args.no_web,
                args.show_context,
            )
        elif args.command == "answer":
            return answer_wiki(
                args.dir,
                " ".join(args.question),
                args.top_k,
                args.retrieval,
                args.graph_rerank,
                args.provider,
                args.model,
                args.api_key_env,
                args.base_url,
                args.max_output_tokens,
                args.graph_rerank_output_tokens,
                args.web_on_gaps,
                args.web_gap_top_k,
                args.web_gap_max_sources,
                args.web_gap_wiki_weight,
                args.web_gap_web_weight,
            )
        elif args.command == "capture":
            capture_source(args.dir, args.source, args.title)
        else:
            parser.error(f"Unknown command: {args.command}")
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
