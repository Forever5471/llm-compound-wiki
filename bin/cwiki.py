#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib import error as urlerror
from urllib import request
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = PROJECT_ROOT / "templates"
WIKI_SECTIONS = ["summaries", "entities", "concepts", "comparisons"]
IGNORED_WIKI_FILES = {"index.md", "log.md"}
DEFAULT_TOP_K = 6
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


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    return True


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
        "raw/**\n!raw/.gitkeep\n.cwiki/prompts/**\n!.cwiki/prompts/.gitkeep\n.DS_Store\n",
    )

    replacements = {"{{domain}}": wiki_domain, "{{date}}": date}
    for template_name in ["WIKI_SCHEMA.md", "CLAUDE.md"]:
        content = (TEMPLATE_ROOT / template_name).read_text(encoding="utf-8")
        for key, value in replacements.items():
            content = content.replace(key, value)
        write_if_missing(root / template_name, content)
    write_if_missing(root / "AGENTS.md", (TEMPLATE_ROOT / "AGENTS.md").read_text(encoding="utf-8"))

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
- Initialized index and log
""",
    )

    print(f"Initialized LLM Compound Wiki at {root}")
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
    terms = [term for term in re.split(r"[\s，。？！,.?;:：；、]+", query.lower().strip()) if term and term not in STOPWORDS]
    if not terms:
        terms = [term for term in re.split(r"[\s，。？！,.?;:：；、]+", query.lower().strip()) if term]
    if not terms:
        return []
    hits: list[tuple[Page, int]] = []
    for page in pages:
        haystack = f"{page.title}\n{page.summary}\n{page.tags}\n{page.text}".lower()
        title_slug = f"{page.title} {page.slug}".lower()
        score = sum(haystack.count(term) for term in terms)
        score += sum(title_slug.count(term) * 4 for term in terms)
        if query.lower() in haystack:
            score += 3
        if score > 0:
            hits.append((page, score))
    hits.sort(key=lambda hit: (-hit[1], hit[0].slug))
    return hits[:limit]


def compact_page_context(page: Page, max_chars: int = 3500) -> str:
    text = page.text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n... [truncated for prompt context]"


def create_query_prompt(target: str, question: str, top_k: int = DEFAULT_TOP_K) -> tuple[Path, list[tuple[Page, int]], str]:
    root = Path(target).resolve()
    assert_wiki(root)
    pages = collect_pages(root)
    hits = find_hits(pages, question, limit=top_k)
    date = today()
    slug = slugify(question)
    ensure_dir(root / ".cwiki" / "prompts")
    prompt_file = root / ".cwiki" / "prompts" / f"query-{date}-{slug}.md"

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
    return prompt_file, hits, prompt


def ask_wiki(target: str, question: str, top_k: int = DEFAULT_TOP_K, show_context: bool = False) -> None:
    root = Path(target).resolve()
    prompt_file, hits, prompt = create_query_prompt(target, question, top_k)
    print(f"Created query prompt: {prompt_file.relative_to(root).as_posix()}")
    if hits:
        print("Relevant pages:")
        for page, score in hits:
            print(f"- [[{page.slug}]] ({score}) {page.rel}")
    else:
        print("Relevant pages: no direct matches")
    if show_context:
        print("\n--- Query Prompt ---")
        print(prompt)


def answer_wiki(
    target: str,
    question: str,
    top_k: int,
    provider: str,
    model: str,
    api_key_env: str,
    max_output_tokens: int,
) -> int:
    if provider != "openai":
        raise RuntimeError(f"Unsupported provider: {provider}. Currently supported: openai")

    root = Path(target).resolve()
    prompt_file, hits, prompt = create_query_prompt(target, question, top_k)
    api_key = os.environ.get(api_key_env)
    if not api_key:
        print(f"Created query prompt: {prompt_file.relative_to(root).as_posix()}")
        raise RuntimeError(f"Missing API key. Set {api_key_env}=... or use `cwiki ask` for context-only mode.")

    instructions = (
        "You answer questions against a local LLM Compound Wiki. "
        "Use only the provided wiki context. Cite local pages as [[slug]] and cite source paths or URLs from claim ledgers. "
        "If the context is insufficient, say exactly what is missing. "
        "Do not invent facts outside the context pack."
    )
    answer = call_openai_responses(api_key, model, instructions, prompt, max_output_tokens)
    answer_file = write_answer_file(root, question, answer, prompt_file, hits, provider, model)

    print(answer)
    print(f"\nSaved answer: {answer_file.relative_to(root).as_posix()}")
    print(f"Query prompt: {prompt_file.relative_to(root).as_posix()}")
    return 0


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
    answer_file = answers_dir / f"answer-{date}-{slug}.md"
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
        text = absolute.read_text(encoding="utf-8")
        body = f"""---
title: {source_title}
source: {absolute}
captured: {date}
type: file
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
2. Identify existing summaries, entities, concepts, comparisons, overview, or synthesis pages to update.
3. Extract source-backed claims into claim ledgers.
4. Add bidirectional wikilinks where appropriate.
5. Run `cwiki index .`.
6. Append to `wiki/log.md`.
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
  cwiki answer . "What does this wiki know about retrieval?" --model gpt-5.2
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

    answer_parser = subparsers.add_parser("answer", help="Answer a question using a model and wiki context")
    answer_parser.add_argument("dir")
    answer_parser.add_argument("question", nargs="+")
    answer_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    answer_parser.add_argument("--provider", default="openai")
    answer_parser.add_argument("--model", default=os.environ.get("CWIKI_OPENAI_MODEL", "gpt-5.2"))
    answer_parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
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
        elif args.command == "answer":
            return answer_wiki(
                args.dir,
                " ".join(args.question),
                args.top_k,
                args.provider,
                args.model,
                args.api_key_env,
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
