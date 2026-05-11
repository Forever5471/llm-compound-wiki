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
            ".env\n"
            ".DS_Store\n"
        ),
    )

    replacements = {"{{domain}}": wiki_domain, "{{date}}": date}
    for template_name in ["WIKI_SCHEMA.md", "CLAUDE.md"]:
        content = (TEMPLATE_ROOT / template_name).read_text(encoding="utf-8")
        for key, value in replacements.items():
            content = content.replace(key, value)
        write_if_missing(root / template_name, content)
    write_if_missing(root / "AGENTS.md", (TEMPLATE_ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    write_if_missing(root / ".env.example", env_example_content())

    copy_skills(root)
    write_if_missing(root / "wiki" / "overview.md", starter_page("Overview", "overview", wiki_domain, date))
    write_if_missing(
        root / "wiki" / "synthesis.md",
        starter_page("Synthesis", "synthesis", "Current cross-source synthesis. The LLM maintains this as the wiki matures.", date),
    )
    write_if_missing(root / "wiki" / "index.md", render_index([]))
    write_if_missing(
        root / "wiki" / "log.md",
        f"""# Operation Log

Append-only, never modify history.

Format: `## [YYYY-MM-DD] operation | title`

---

## [{date}] init | {wiki_domain}
- Created wiki structure
- Created CLAUDE.md, WIKI_SCHEMA.md, and AGENTS.md
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


def find_hits(pages: list[Page], query: str, limit: int) -> list[tuple[Page, int]]:
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


def create_query_prompt(target: str, question: str, top_k: int = DEFAULT_TOP_K) -> tuple[Path, Path, list[tuple[Page, int]], str, str]:
    root = Path(target).resolve()
    assert_wiki(root)
    pages = collect_pages(root)
    hits = find_hits(pages, question, limit=top_k)
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
---

# Query Prompt - {question}

## Question

{question}

## Relevant Pages

{relevant_pages}

## Instructions For The Agent

1. Read `CLAUDE.md` and `WIKI_SCHEMA.md`.
2. Read `wiki/index.md`.
3. Read the relevant pages below in full from disk before answering.
4. Answer using local citations like `[[slug]]` and source paths or URLs from claim ledgers.
5. State gaps explicitly if the wiki does not contain enough evidence.
6. If the answer is valuable, offer to save it into `wiki/synthesis.md`, `wiki/comparisons/`, or another fitting wiki page.
7. If saved, run `cwiki index .` and append to `wiki/log.md`.

## Context Pack

{context_sections}
"""
    prompt_file.write_text(prompt, encoding="utf-8")
    brief = render_human_brief(question, hits)
    brief_file.write_text(brief, encoding="utf-8")
    return prompt_file, brief_file, hits, prompt, brief


def render_human_brief(question: str, hits: list[tuple[Page, int]]) -> str:
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


def ask_wiki(target: str, question: str, top_k: int = DEFAULT_TOP_K, show_context: bool = False) -> None:
    root = Path(target).resolve()
    prompt_file, brief_file, hits, prompt, brief = create_query_prompt(target, question, top_k)
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


def create_web_query_prompt(
    target: str,
    question: str,
    top_k: int = DEFAULT_TOP_K,
    max_web_sources: int = 6,
    wiki_weight: float = DEFAULT_WIKI_WEIGHT,
    web_weight: float = DEFAULT_WEB_WEIGHT,
    web_enabled: bool = True,
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
    research = render_web_research_template(question, hits, wiki_weight, web_weight, web_mode, effective_web_sources)
    research_file.write_text(research, encoding="utf-8")
    fusion_prompt = render_fusion_prompt(question, hits, research_file, wiki_weight, web_weight, web_mode)
    fusion_prompt_file.write_text(fusion_prompt, encoding="utf-8")
    brief = render_web_brief(question, hits, prompt_file, fusion_prompt_file, research_file, effective_web_sources, wiki_weight, web_weight, web_mode)
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
) -> str:
    date = today()
    relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}` — {page.summary}" for page, score in hits)
    if not relevant_pages:
        relevant_pages = "- No direct local matches"
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
) -> str:
    date = today()
    relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}`" for page, score in hits)
    if not relevant_pages:
        relevant_pages = "- No direct local matches"
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
) -> str:
    date = today()
    chinese = contains_chinese(question) or any(contains_chinese(page.text) for page, _ in hits)
    relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}` — {page.summary}" for page, score in hits)
    if not relevant_pages:
        relevant_pages = "- No direct local matches"

    if chinese:
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


def answer_wiki(
    target: str,
    question: str,
    top_k: int,
    provider: str,
    model: str | None,
    api_key_env: str | None,
    base_url: str | None,
    max_output_tokens: int,
) -> int:
    root = Path(target).resolve()
    load_local_env(root)
    provider = (provider or os.environ.get("CWIKI_PROVIDER") or "openai").lower()
    model = resolve_model(provider, model)
    api_key_env = resolve_api_key_env(provider, api_key_env)
    base_url = resolve_base_url(provider, base_url)

    if provider not in {"openai", "glm"}:
        raise RuntimeError(f"Unsupported provider: {provider}. Currently supported: openai, glm")

    prompt_file, brief_file, hits, prompt, _brief = create_query_prompt(target, question, top_k)
    api_key = os.environ.get(api_key_env)
    if not api_key:
        print(f"Created query prompt: {prompt_file.relative_to(root).as_posix()}")
        print(f"Created human brief: {brief_file.relative_to(root).as_posix()}")
        raise RuntimeError(f"Missing API key. Set {api_key_env}=... or use `cwiki ask` for context-only mode.")

    instructions = (
        "You answer questions against a local LLM Compound Wiki. "
        "Use only the provided wiki context. Cite local pages as [[slug]] and cite source paths or URLs from claim ledgers. "
        "If the context is insufficient, say exactly what is missing. "
        "Do not invent facts outside the context pack."
    )
    if provider == "openai":
        answer = call_openai_responses(api_key, model, instructions, prompt, max_output_tokens)
    else:
        answer = call_openai_compatible_chat(
            api_key=api_key,
            base_url=base_url,
            provider_name="GLM",
            model=model,
            instructions=instructions,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
        )
    answer_file = write_answer_file(root, question, answer, prompt_file, hits, provider, model)

    print(answer)
    print(f"\nSaved answer: {answer_file.relative_to(root).as_posix()}")
    print(f"Query prompt: {prompt_file.relative_to(root).as_posix()}")
    return 0


def resolve_model(provider: str, model: str | None) -> str:
    if model:
        return model
    if provider == "glm":
        return os.environ.get("CWIKI_GLM_MODEL") or os.environ.get("CWIKI_MODEL") or DEFAULT_GLM_MODEL
    return os.environ.get("CWIKI_OPENAI_MODEL") or os.environ.get("CWIKI_MODEL") or DEFAULT_OPENAI_MODEL


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


def call_openai_responses(api_key: str, model: str, instructions: str, prompt: str, max_output_tokens: int) -> str:
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
    return text


def call_openai_compatible_chat(
    api_key: str,
    base_url: str,
    provider_name: str,
    model: str,
    instructions: str,
    prompt: str,
    max_output_tokens: int,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_output_tokens,
    }
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
        raise RuntimeError(f"{provider_name} API returned no text output.")
    return text


def extract_chat_completion_text(data: dict[str, object]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list):
        return ""
    chunks: list[str] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
    return "\n".join(chunk for chunk in chunks if chunk).strip()


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
) -> Path:
    date = today()
    slug = slugify(question)
    answers_dir = root / ".cwiki" / "answers"
    ensure_dir(answers_dir)
    answer_file = answers_dir / f"answer-{timestamp()}-{slug}.md"
    relevant_pages = "\n".join(f"- [[{page.slug}]] ({score}) `{page.rel}`" for page, score in hits) or "- No direct matches"
    answer_file.write_text(
        f"""---
title: Answer - {question}
tags: [answer]
sources: {len(hits)}
updated: {date}
status: draft
provider: {provider}
model: {model}
---

# Answer - {question}

## Question

{question}

## Answer

{answer}

## Relevant Pages

{relevant_pages}

## Query Prompt

`{prompt_file.relative_to(root).as_posix()}`
""",
        encoding="utf-8",
    )
    return answer_file


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
4. Extract source-backed claims into claim ledgers.
5. Add bidirectional wikilinks where appropriate.
6. Run `cwiki index .`.
7. Append to `wiki/log.md`.
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

    search_parser = subparsers.add_parser("search", help="Search wiki pages")
    search_parser.add_argument("dir")
    search_parser.add_argument("query", nargs="+")

    ask_parser = subparsers.add_parser("ask", help="Create a query prompt from wiki context")
    ask_parser.add_argument("dir")
    ask_parser.add_argument("question", nargs="+")
    ask_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
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
    answer_parser.add_argument("--provider", default=None)
    answer_parser.add_argument("--model", default=None)
    answer_parser.add_argument("--api-key-env", default=None)
    answer_parser.add_argument("--base-url", default=None)
    answer_parser.add_argument("--max-output-tokens", type=int, default=1200)

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
        elif args.command == "search":
            search_wiki(args.dir, " ".join(args.query))
        elif args.command == "ask":
            ask_wiki(args.dir, " ".join(args.question), args.top_k, args.show_context)
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
                args.provider,
                args.model,
                args.api_key_env,
                args.base_url,
                args.max_output_tokens,
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
