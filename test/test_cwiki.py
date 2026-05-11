import datetime as dt
import subprocess
import sys
import tempfile
import unittest
import zipfile
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
            self.assertTrue((root / ".env.example").exists())
            self.assertTrue((root / "wiki" / "index.md").exists())
            self.assertTrue((root / "wiki" / "overview.md").exists())
            self.assertTrue((root / "wiki" / "synthesis.md").exists())
            self.assertTrue((root / "wiki" / "summaries").exists())
            self.assertTrue((root / "wiki" / "entities").exists())
            self.assertTrue((root / "wiki" / "concepts").exists())
            self.assertTrue((root / "wiki" / "comparisons").exists())
            gitignore = (root / ".gitignore").read_text()
            self.assertIn(".env", gitignore)
            self.assertIn(".cwiki/briefs/**", gitignore)
            self.assertIn(".cwiki/answers/**", gitignore)
            self.assertIn(".cwiki/web-research/**", gitignore)
            self.assertIn(".cwiki/eval/**", gitignore)
            self.assertTrue((root / ".claude" / "skills" / "wiki-init" / "SKILL.md").exists())
            self.assertTrue((root / ".agents" / "skills" / "wiki-ingest" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-parse-docx" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-parse-pdf" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-parse-image" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-parse-pptx" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-parse-xlsx" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-agent-browser" / "SKILL.md").exists())

            self.assertIn("Domain: Test knowledge", (root / "WIKI_SCHEMA.md").read_text())
            env_example = (root / ".env.example").read_text()
            self.assertIn("CWIKI_PROVIDER=glm", env_example)
            self.assertIn("OPENAI_API_KEY=replace-with-your-local-key", env_example)
            self.assertIn("CWIKI_WEB_WIKI_WEIGHT=0.6", env_example)
            overview = (root / "wiki" / "overview.md").read_text(encoding="utf-8")
            self.assertIn("Entry Decision", overview)
            self.assertIn("Current Map", overview)
            self.assertIn("[[synthesis]]", overview)
            self.assertIn("status: seed", overview)
            synthesis = (root / "wiki" / "synthesis.md").read_text(encoding="utf-8")
            self.assertIn("Current Thesis", synthesis)
            self.assertIn("Stable Claims", synthesis)
            self.assertIn("[[overview]]", synthesis)
            self.assertIn("status: seed", synthesis)
            claude = (root / "CLAUDE.md").read_text()
            self.assertIn("Domain: Test knowledge", claude)
            self.assertIn("The human owns `raw/`; the LLM owns `wiki/`", claude)
            self.assertIn("The CLI is the scaffold and local utility layer", claude)
            self.assertIn("ask` and `web-ask` prepare evidence and prompts", claude)
            self.assertIn("they do not change this agent platform's active chat model", claude)
            self.assertIn("does not perform live web search", claude)
            self.assertIn("does not execute browser research by itself", claude)
            self.assertIn("not executable CLI plugins", claude)
            self.assertIn("use the current agent model for reasoning and final prose", claude)
            self.assertIn("Prefer this folder's local instructions and skills", claude)
            self.assertIn("If the local skills do not cover the task", claude)
            agents = (root / "AGENTS.md").read_text()
            self.assertIn("The CLI is the scaffold and local utility layer", agents)
            self.assertIn("ask` and `web-ask` prepare evidence and prompts", agents)
            self.assertIn("they do not change this agent platform's active chat model", agents)
            self.assertIn("does not perform live web search", agents)
            self.assertIn("does not execute browser research by itself", agents)
            self.assertIn("not executable CLI plugins", agents)
            self.assertIn("use the current agent model for reasoning and final prose", agents)
            self.assertIn("Prefer this folder's local instructions and skills", agents)
            self.assertIn("If the local skills do not cover the task", agents)

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

    def test_eval_reports_wiki_quality_and_writes_traceable_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Eval test")
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

Retrieval finds relevant evidence before synthesis. This page contains enough explanatory detail to require an
evidence ledger in deterministic wiki evaluation, because the project needs factual claims to stay traceable.

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| Retrieval finds relevant evidence before synthesis. |  | high | 2026-05-10 |
""",
                encoding="utf-8",
            )

            result = run_cwiki("eval", str(root))
            self.assertIn("# Wiki Evaluation", result.stdout)
            self.assertIn("## Deterministic Evaluation", result.stdout)
            self.assertIn("Evidence:", result.stdout)
            self.assertIn("Saved evaluation report: .cwiki/eval/wiki-eval-", result.stdout)

            reports = list((root / ".cwiki" / "eval").glob("wiki-eval-*.md"))
            self.assertEqual(len(reports), 1)
            report = reports[0].read_text(encoding="utf-8")
            self.assertIn("mode: wiki", report)
            self.assertIn("llm_assisted: false", report)
            self.assertIn("evaluated_at:", report)
            self.assertIn("Claim Ledger row", report)
            self.assertIn("[P1]", report)

            index = (root / ".cwiki" / "eval" / "index.md").read_text(encoding="utf-8")
            self.assertIn("| wiki |", index)
            self.assertIn(reports[0].name, index)

    def test_eval_no_write_does_not_create_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Eval no write test")

            result = run_cwiki("eval", str(root), "--no-write")
            self.assertIn("# Wiki Evaluation", result.stdout)
            self.assertNotIn("Saved evaluation report:", result.stdout)
            self.assertNotIn("Overview appears to be a stub", result.stdout)
            self.assertNotIn("Synthesis appears to be a stub", result.stdout)
            self.assertNotIn("Factual wiki page has no Claim Ledger", result.stdout)
            self.assertFalse((root / ".cwiki" / "eval").exists())

    def test_eval_uses_chinese_report_for_chinese_wiki_and_accepts_web_research_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "中文评估测试")
            (root / "wiki" / "concepts" / "检索.md").write_text(
                """---
title: 检索
kind: concept
tags: [搜索, 证据]
sources: 1
updated: 2026-05-10
status: active
---

# 检索

检索是在生成答案前寻找相关证据的过程。它可以帮助 agent 把回答建立在已有 wiki 和外部研究记录之上，
也能让后续维护者追踪某个结论来自哪里。

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| 检索是在生成答案前寻找相关证据的过程。 | .cwiki/web-research/web-research-retrieval.md | high | 2026-05-10 |
""",
                encoding="utf-8",
            )

            result = run_cwiki("eval", str(root))
            self.assertIn("# Wiki 质量评估", result.stdout)
            self.assertIn("## 确定性评估", result.stdout)
            self.assertIn("证据：", result.stdout)
            self.assertIn("report_language: zh-CN", result.stdout)
            self.assertNotIn("source is not clearly traceable", result.stdout)
            self.assertNotIn("source 不够清晰可追溯", result.stdout)

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
            prompt_text = prompt.read_text()
            self.assertIn("Preserve the source language", prompt_text)
            self.assertIn("Check `wiki/overview.md` and `wiki/synthesis.md`", prompt_text)
            self.assertIn("status: seed", prompt_text)
            self.assertIn("Whether `wiki/overview.md` changed", prompt_text)
            self.assertIn("Whether `wiki/synthesis.md` changed", prompt_text)

    def test_capture_extracts_docx_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Docx capture test")
            docx = root / "source.docx"
            document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>中文 DOCX 摄入测试</w:t></w:r></w:p>
    <w:p><w:r><w:t>保留源语言。</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
            with zipfile.ZipFile(docx, "w") as archive:
                archive.writestr("word/document.xml", document_xml)

            run_cwiki("capture", str(root), str(docx), "--title", "DOCX 测试")
            raw_file = root / "raw" / "captures" / f"{dt.date.today().isoformat()}-docx-测试.md"
            raw = raw_file.read_text()
            self.assertIn("type: docx", raw)
            self.assertIn("中文 DOCX 摄入测试", raw)

    def test_capture_extracts_pptx_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "PPTX capture test")
            pptx = root / "source.pptx"
            slide_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>OpenClaw 介绍</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
</p:sld>
"""
            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", slide_xml)

            run_cwiki("capture", str(root), str(pptx), "--title", "PPTX 测试")
            raw_file = root / "raw" / "captures" / f"{dt.date.today().isoformat()}-pptx-测试.md"
            raw = raw_file.read_text()
            self.assertIn("type: pptx", raw)
            self.assertIn("## Slide 1", raw)
            self.assertIn("OpenClaw 介绍", raw)

    def test_capture_extracts_xlsx_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "XLSX capture test")
            xlsx = root / "source.xlsx"
            shared_strings = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>指标</t></si>
  <si><t>自愈成功率</t></si>
</sst>
"""
            sheet = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>2026</v></c></row>
    <row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>0.8</v></c></row>
  </sheetData>
</worksheet>
"""
            with zipfile.ZipFile(xlsx, "w") as archive:
                archive.writestr("xl/sharedStrings.xml", shared_strings)
                archive.writestr("xl/worksheets/sheet1.xml", sheet)

            run_cwiki("capture", str(root), str(xlsx), "--title", "XLSX 测试")
            raw_file = root / "raw" / "captures" / f"{dt.date.today().isoformat()}-xlsx-测试.md"
            raw = raw_file.read_text()
            self.assertIn("type: xlsx", raw)
            self.assertIn("## Sheet 1", raw)
            self.assertIn("自愈成功率 | 0.8", raw)

    def test_capture_records_image_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Image capture test")
            image = root / "source.png"
            image.write_bytes(b"not-a-real-image-but-a-reference")

            run_cwiki("capture", str(root), str(image), "--title", "图片测试")
            raw_file = root / "raw" / "captures" / f"{dt.date.today().isoformat()}-图片测试.md"
            raw = raw_file.read_text()
            self.assertIn("type: image", raw)
            self.assertIn("wiki-parse-image", raw)

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

    def test_web_ask_creates_browser_prompt_with_traceable_source_rules(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Web ask test")
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
                "web-ask",
                str(root),
                "What changed recently about retrieval?",
                "--max-web-sources",
                "4",
                "--wiki-weight",
                "0.7",
                "--web-weight",
                "0.3",
            )
            self.assertIn("Created web query prompt:", result.stdout)
            self.assertIn("Created web brief:", result.stdout)
            self.assertIn("Created web research workspace:", result.stdout)
            self.assertIn("Created evidence fusion prompt:", result.stdout)
            self.assertIn("Evidence weights: wiki=0.7, web=0.3, web_mode=enabled", result.stdout)
            self.assertIn("the CLI does not browse by itself", result.stdout)
            self.assertIn("[[retrieval]]", result.stdout)

            prompt = root / ".cwiki" / "prompts" / f"web-query-{dt.date.today().isoformat()}-what-changed-recently-about-retrieval.md"
            fusion = root / ".cwiki" / "prompts" / f"fusion-{dt.date.today().isoformat()}-what-changed-recently-about-retrieval.md"
            brief = root / ".cwiki" / "briefs" / f"web-brief-{dt.date.today().isoformat()}-what-changed-recently-about-retrieval.md"
            research = root / ".cwiki" / "web-research" / f"web-research-{dt.date.today().isoformat()}-what-changed-recently-about-retrieval.md"
            self.assertTrue(prompt.exists())
            self.assertTrue(fusion.exists())
            self.assertTrue(brief.exists())
            self.assertTrue(research.exists())
            prompt_text = prompt.read_text()
            self.assertIn("wiki-agent-browser", prompt_text)
            self.assertIn("Search the web for up to 4 high-quality sources", prompt_text)
            self.assertIn("Do not cite search result snippets", prompt_text)
            self.assertIn("For every external factual claim, cite a URL", prompt_text)
            self.assertIn("Local wiki weight: 0.7", prompt_text)
            self.assertIn("Web search weight: 0.3", prompt_text)
            self.assertIn("web_mode: enabled", research.read_text())
            self.assertIn("Evidence Fusion Prompt", fusion.read_text())

    def test_web_ask_can_disable_web_research(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "No web test")
            result = run_cwiki(
                "web-ask",
                str(root),
                "Answer from local wiki only",
                "--no-web",
                "--web-weight",
                "0",
            )

            self.assertIn("web_mode=disabled", result.stdout)
            prompt = root / ".cwiki" / "prompts" / f"web-query-{dt.date.today().isoformat()}-answer-from-local-wiki-only.md"
            research = root / ".cwiki" / "web-research" / f"web-research-{dt.date.today().isoformat()}-answer-from-local-wiki-only.md"
            self.assertIn("Web mode: disabled", prompt.read_text())
            self.assertIn("Search the web for up to 0 high-quality sources", prompt.read_text())
            self.assertIn("web_mode: disabled", research.read_text())

    def test_web_ask_reads_defaults_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Web env test")
            (root / ".env").write_text(
                "\n".join(
                    [
                        "CWIKI_WEB_WIKI_WEIGHT=0.8",
                        "CWIKI_WEB_WEIGHT=0.2",
                        "CWIKI_WEB_MAX_SOURCES=3",
                        "CWIKI_WEB_ENABLED=false",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_cwiki("web-ask", str(root), "Use env web defaults")
            self.assertIn("Evidence weights: wiki=0.8, web=0.2, web_mode=disabled", result.stdout)

            prompt = root / ".cwiki" / "prompts" / f"web-query-{dt.date.today().isoformat()}-use-env-web-defaults.md"
            text = prompt.read_text()
            self.assertIn("Local wiki weight: 0.8", text)
            self.assertIn("Web search weight: 0.2", text)
            self.assertIn("Web mode: disabled", text)
            self.assertIn("Search the web for up to 0 high-quality sources", text)

    def test_answer_supports_glm_provider_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "GLM answer test")
            result = run_cwiki(
                "answer",
                str(root),
                "测试 GLM 配置",
                "--provider",
                "glm",
                "--api-key-env",
                "CWIKI_TEST_MISSING_GLM_KEY",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Created query prompt:", result.stdout)
            self.assertIn("Missing API key", result.stderr)

    def test_chinese_ask_creates_chinese_human_brief(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "中文 brief 测试")
            (root / "wiki" / "concepts" / "gray-zone-arbitration.md").write_text(
                """---
title: 灰区仲裁设计
kind: concept
tags: [rpa, gray_zone]
sources: 1
updated: 2026-05-10
status: active
---

# 灰区仲裁设计

gray_zone 是自愈链路里的模糊样本处理层。

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| gray_zone 在 Top-K 不够确定时触发。 | raw/source.md | high | 2026-05-10 |
""",
                encoding="utf-8",
            )
            run_cwiki("ask", str(root), "gray_zone是怎么设计的")
            brief = root / ".cwiki" / "briefs" / f"brief-{dt.date.today().isoformat()}-gray-zone是怎么设计的.md"
            text = brief.read_text()
            self.assertIn("## 问题", text)
            self.assertIn("## 简短结论", text)
            self.assertIn("## 关键声明", text)

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

    def test_hybrid_search_uses_wikilink_relationships(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Hybrid search test")
            (root / "wiki" / "concepts" / "semantic-self-healing-engine.md").write_text(
                """---
title: 语义自愈引擎
kind: concept
tags: [rpa]
sources: 1
updated: 2026-05-10
status: active
---

# 语义自愈引擎

该引擎处理定位失败后的恢复，并关联 [[gray-zone-arbitration]]。
""",
                encoding="utf-8",
            )
            (root / "wiki" / "concepts" / "gray-zone-arbitration.md").write_text(
                """---
title: 灰区仲裁设计
kind: concept
tags: [rpa]
sources: 1
updated: 2026-05-10
status: active
---

# 灰区仲裁设计

Top-K 不确定时进入裁决。
""",
                encoding="utf-8",
            )

            result = run_cwiki("ask", str(root), "定位失败后怎么恢复？")
            self.assertIn("[[semantic-self-healing-engine]]", result.stdout)
            self.assertIn("[[gray-zone-arbitration]]", result.stdout)

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
