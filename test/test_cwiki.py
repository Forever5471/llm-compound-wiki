import datetime as dt
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "cwiki.py"


def run_cwiki(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


class CwikiTest(unittest.TestCase):
    def test_init_creates_a_usable_wiki(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Test knowledge")

            self.assertTrue((root / "WIKI_SCHEMA.md").exists())
            self.assertTrue((root / "CLAUDE.md").exists())
            self.assertTrue((root / "AGENTS.md").exists())
            self.assertTrue((root / "wiki" / "index.md").exists())
            self.assertTrue((root / "wiki" / "overview.md").exists())
            self.assertTrue((root / "wiki" / "synthesis.md").exists())
            self.assertTrue((root / "wiki" / "summaries").exists())
            self.assertTrue((root / "wiki" / "entities").exists())
            self.assertTrue((root / "wiki" / "concepts").exists())
            self.assertTrue((root / "wiki" / "comparisons").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-init" / "SKILL.md").exists())
            self.assertTrue((root / ".agents" / "skills" / "wiki-ingest" / "SKILL.md").exists())

            self.assertIn("Domain: Test knowledge", (root / "WIKI_SCHEMA.md").read_text())
            claude = (root / "CLAUDE.md").read_text()
            self.assertIn("Domain: Test knowledge", claude)
            self.assertIn("The human owns `raw/`; the LLM owns `wiki/`", claude)

    def test_index_lists_generated_wiki_sections(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Index test")

            (root / "wiki" / "concepts" / "retrieval.md").write_text(
                """---
title: Retrieval
kind: concept
tags: [ai]
sources: 1
updated: 2026-05-08
status: active
---

# Retrieval

Finding relevant evidence.
""",
                encoding="utf-8",
            )
            (root / "wiki" / "comparisons" / "rag-vs-llm-wiki.md").write_text(
                """---
title: RAG vs LLM Wiki
kind: comparison
tags: [analysis]
sources: 1
updated: 2026-05-08
---

# RAG vs LLM Wiki
""",
                encoding="utf-8",
            )

            run_cwiki("index", str(root))
            index = (root / "wiki" / "index.md").read_text()
            self.assertIn("[[retrieval]]", index)
            self.assertIn("[[rag-vs-llm-wiki]]", index)
            self.assertIn("Concept Pages", index)
            self.assertIn("Comparisons", index)

    def test_lint_reports_broken_links(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Lint test")
            (root / "wiki" / "concepts" / "a.md").write_text(
                """---
title: A
kind: concept
tags: [test]
sources: 1
updated: 2026-05-08
---

# A

Links to [[missing-page]].
""",
                encoding="utf-8",
            )
            result = run_cwiki("lint", str(root), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Broken links: 1", result.stdout)

    def test_lint_ignores_wikilinks_inside_code_spans(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Code link test")
            (root / "wiki" / "concepts" / "code-example.md").write_text(
                """---
title: Code Example
kind: concept
tags: [test]
sources: 1
updated: 2026-05-10
---

# Code Example

Inline code `[[not-a-real-link]]` should not count.

```markdown
[[also-not-real]]
```
""",
                encoding="utf-8",
            )
            result = run_cwiki("lint", str(root))
            self.assertIn("Broken links: 0", result.stdout)

    def test_capture_creates_raw_record_and_ingest_prompt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Capture test")
            run_cwiki("capture", str(root), "https://example.com/some-article", "--title", "Some Article")

            self.assertTrue((root / "raw" / "captures").exists())
            prompt = root / ".cwiki" / "prompts" / f"ingest-{dt.date.today().isoformat()}-some-article.md"
            self.assertTrue(prompt.exists())

    def test_ask_creates_query_prompt_from_wiki_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Ask test")
            (root / "wiki" / "concepts" / "retrieval.md").write_text(
                """---
title: Retrieval
kind: concept
tags: [rag, search]
sources: 1
updated: 2026-05-10
status: active
---

# Retrieval

Retrieval finds relevant evidence before synthesis.

## Related

- [[synthesis]] - global synthesis
""",
                encoding="utf-8",
            )

            result = run_cwiki("ask", str(root), "What does the wiki know about retrieval?")
            self.assertIn("Created query prompt:", result.stdout)
            self.assertIn("Created human brief:", result.stdout)
            self.assertIn("[[retrieval]]", result.stdout)

            prompt = root / ".cwiki" / "prompts" / f"query-{dt.date.today().isoformat()}-what-does-the-wiki-know-about-retrieval.md"
            brief = root / ".cwiki" / "briefs" / f"brief-{dt.date.today().isoformat()}-what-does-the-wiki-know-about-retrieval.md"
            self.assertTrue(prompt.exists())
            self.assertTrue(brief.exists())
            text = prompt.read_text()
            self.assertIn("## Question", text)
            self.assertIn("[[retrieval]]", text)
            self.assertIn("Answer using local citations", text)
            brief_text = brief.read_text()
            self.assertIn("## Short Takeaway", brief_text)
            self.assertIn("[[retrieval]]", brief_text)

    def test_ask_matches_mixed_chinese_english_query(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Chinese query test")
            (root / "wiki" / "concepts" / "rpa-self-healing.md").write_text(
                """---
title: RPA 自愈
kind: concept
tags: [rpa, self-healing]
sources: 1
updated: 2026-05-10
status: active
---

# RPA 自愈

RPA 自愈通过候选召回、语义匹配、风险分级和结果校验恢复流程。
""",
                encoding="utf-8",
            )

            result = run_cwiki("ask", str(root), "如何实现rpa自愈？")
            self.assertIn("[[rpa-self-healing]]", result.stdout)

    def test_answer_without_api_key_creates_prompt_and_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Answer test")
            (root / "wiki" / "concepts" / "retrieval.md").write_text(
                """---
title: Retrieval
kind: concept
tags: [rag, search]
sources: 1
updated: 2026-05-10
status: active
---

# Retrieval

Retrieval finds relevant evidence before synthesis.
""",
                encoding="utf-8",
            )

            result = run_cwiki(
                "answer",
                str(root),
                "What does the wiki know about retrieval?",
                "--api-key-env",
                "CWIKI_TEST_MISSING_OPENAI_KEY",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Created query prompt:", result.stdout)
            self.assertIn("Created human brief:", result.stdout)
            self.assertIn("Missing API key", result.stderr)
            prompt = root / ".cwiki" / "prompts" / f"query-{dt.date.today().isoformat()}-what-does-the-wiki-know-about-retrieval.md"
            brief = root / ".cwiki" / "briefs" / f"brief-{dt.date.today().isoformat()}-what-does-the-wiki-know-about-retrieval.md"
            self.assertTrue(prompt.exists())
            self.assertTrue(brief.exists())


if __name__ == "__main__":
    unittest.main()
