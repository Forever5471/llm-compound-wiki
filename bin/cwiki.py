#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = PROJECT_ROOT / "templates"
WIKI_SECTIONS = ["summaries", "entities", "concepts", "comparisons"]
IGNORED_WIKI_FILES = {"index.md", "log.md"}


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
    q = query.lower()
    hits = []
    for page in collect_pages(root):
        haystack = f"{page.title}\n{page.summary}\n{page.text}".lower()
        count = haystack.count(q)
        if count > 0:
            hits.append((page, count))
    hits.sort(key=lambda hit: (-hit[1], hit[0].page.slug if hasattr(hit[0], "page") else hit[0].slug))
    hits = hits[:20]

    if not hits:
        print(f'No matches for "{query}".')
        return
    for page, count in hits:
        print(f"- [[{page.slug}]] ({count}) {page.rel}")
        print(f"  {page.summary}")


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
