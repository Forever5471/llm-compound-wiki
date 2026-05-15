import datetime as dt
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "cwiki.py"
SPEC = importlib.util.spec_from_file_location("cwiki_module", CLI)
assert SPEC and SPEC.loader
CWIKI = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CWIKI
SPEC.loader.exec_module(CWIKI)


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
            gitignore = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".env", gitignore)
            self.assertIn(".cwiki/briefs/**", gitignore)
            self.assertIn(".cwiki/answers/**", gitignore)
            self.assertIn(".cwiki/web-research/**", gitignore)
            self.assertIn(".cwiki/eval/**", gitignore)
            self.assertIn(".cwiki/graph/**", gitignore)
            self.assertTrue((root / ".claude" / "skills" / "wiki-init" / "SKILL.md").exists())
            self.assertTrue((root / ".agents" / "skills" / "wiki-ingest" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-parse-docx" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-parse-pdf" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-parse-image" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-parse-pptx" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-parse-xlsx" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "wiki-agent-browser" / "SKILL.md").exists())

            self.assertIn("Domain: Test knowledge", (root / "WIKI_SCHEMA.md").read_text(encoding="utf-8"))
            env_example = (root / ".env.example").read_text(encoding="utf-8")
            self.assertIn("CWIKI_PROVIDER=glm", env_example)
            self.assertIn("OPENAI_API_KEY=replace-with-your-local-key", env_example)
            self.assertIn("CWIKI_EVAL_PROVIDER=glm", env_example)
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
            claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
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
            self.assertIn("Hybrid Agent Query Workflow", claude)
            self.assertIn("Layered Retrieval Strategy", claude)
            self.assertIn("Refresh both `wiki/overview.md` and `wiki/synthesis.md` after every ingest or update", claude)
            agents = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("The CLI is the scaffold and local utility layer", agents)
            self.assertIn("ask` and `web-ask` prepare evidence and prompts", agents)
            self.assertIn("they do not change this agent platform's active chat model", agents)
            self.assertIn("does not perform live web search", agents)
            self.assertIn("does not execute browser research by itself", agents)
            self.assertIn("not executable CLI plugins", agents)
            self.assertIn("use the current agent model for reasoning and final prose", agents)
            self.assertIn("Prefer this folder's local instructions and skills", agents)
            self.assertIn("If the local skills do not cover the task", agents)
            self.assertIn("Hybrid Agent Query Workflow", agents)
            self.assertIn("Layered Retrieval Strategy", agents)
            self.assertIn("Refresh both `wiki/overview.md` and `wiki/synthesis.md` after every ingest or update", agents)
            ingest_skill = (root / ".claude" / "skills" / "wiki-ingest" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("Mandatory global pages refresh", ingest_skill)
            self.assertIn("Open both `wiki/overview.md` and `wiki/synthesis.md` on every ingest", ingest_skill)
            self.assertIn("Do not leave generic placeholder prose after the first real ingest", ingest_skill)
            update_skill = (root / ".claude" / "skills" / "wiki-update" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("Mandatory global pages refresh", update_skill)
            self.assertIn("Open both `wiki/overview.md` and `wiki/synthesis.md` on every update", update_skill)

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
            index = (root / "wiki" / "index.md").read_text(encoding="utf-8")
            self.assertIn("[[retrieval]]", index)
            self.assertIn("[[rag-vs-llm-wiki]]", index)
            self.assertIn("Concept Pages", index)
            self.assertIn("Comparisons", index)

    def test_graph_commands_create_report_path_and_node_explanation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Graph test")
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

Retrieval links to [[retrieval]], [[synthesis]], and [[missing-page]].

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| Retrieval finds relevant evidence before synthesis. | raw/captures/source.md | high | 2026-05-10 |
""",
                encoding="utf-8",
            )
            (root / "wiki" / "concepts" / "reranking.md").write_text(
                """---
title: Reranking
kind: concept
tags: [rag]
sources: 1
updated: 2026-05-10
status: active
---

# Reranking

Reranking links to [[retrieval]].
""",
                encoding="utf-8",
            )

            graph_result = run_cwiki("graph", str(root))
            self.assertIn("Created graph:", graph_result.stdout)
            graph_file = root / ".cwiki" / "graph" / "graph.json"
            graph = json.loads(graph_file.read_text(encoding="utf-8"))
            self.assertEqual(graph["stats"]["node_count"], 4)
            self.assertEqual(graph["stats"]["broken_edge_count"], 1)
            self.assertFalse(any(edge["source"] == edge["target"] for edge in graph["edges"]))
            retrieval = next(node for node in graph["nodes"] if node["id"] == "retrieval")
            self.assertIn("raw/captures/source.md", retrieval["claim_sources"])

            report_result = run_cwiki("graph-report", str(root))
            self.assertIn("Created graph report:", report_result.stdout)
            report = (root / ".cwiki" / "graph" / "graph.md").read_text(encoding="utf-8")
            self.assertIn("Broken Links", report)
            self.assertIn("[[retrieval]] -> [[missing-page]]", report)

            path_result = run_cwiki("path", str(root), "reranking", "synthesis")
            self.assertIn("[[reranking]] -> [[retrieval]] -> [[synthesis]]", path_result.stdout)

            explain_result = run_cwiki("explain", str(root), "retrieval")
            self.assertIn("# [[retrieval]]", explain_result.stdout)
            self.assertIn("[[reranking]]", explain_result.stdout)
            self.assertIn("raw/captures/source.md", explain_result.stdout)

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

    def test_eval_answer_reports_grounded_answer_quality(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Answer eval test")
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

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| Retrieval finds relevant evidence before synthesis. | raw/captures/retrieval.md | high | 2026-05-10 |
""",
                encoding="utf-8",
            )
            answer = root / ".cwiki" / "answers" / "answer-good.md"
            answer.parent.mkdir(parents=True, exist_ok=True)
            answer.write_text(
                """---
title: Answer - Retrieval
tags: [answer]
sources: 1
updated: 2026-05-10
status: draft
question: What does retrieval do?
---

# Answer - Retrieval

## Question

What does retrieval do?

## Answer

Retrieval finds relevant evidence before synthesis, according to [[retrieval]] and `raw/captures/retrieval.md`.

## Gaps

The wiki does not yet compare retrieval strategies.

## Relevant Pages

- [[retrieval]] (10) `wiki/concepts/retrieval.md`
""",
                encoding="utf-8",
            )

            result = run_cwiki("eval-answer", str(root), str(answer))
            self.assertIn("# Answer Evaluation", result.stdout)
            self.assertIn("Risk: low", result.stdout)
            self.assertIn("Saved evaluation report: .cwiki/eval/answer-eval-", result.stdout)

            reports = list((root / ".cwiki" / "eval").glob("answer-eval-*.md"))
            self.assertEqual(len(reports), 1)
            report = reports[0].read_text(encoding="utf-8")
            self.assertIn("mode: answer", report)
            self.assertIn("llm_assisted: false", report)
            self.assertIn("Grounding:", report)
            self.assertIn("Source Use:", report)

            index = (root / ".cwiki" / "eval" / "index.md").read_text(encoding="utf-8")
            self.assertIn("| answer |", index)
            self.assertIn(reports[0].name, index)

    def test_eval_json_outputs_parseable_structured_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Eval json test")

            result = run_cwiki("eval", str(root), "--json")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["deterministic"]["mode"], "wiki")
            self.assertIn("overall", payload["deterministic"]["scores"])
            self.assertIn("signals", payload["deterministic"])
            self.assertIsNone(payload["llm_assisted"])
            self.assertNotIn("Saved evaluation report:", result.stdout)
            self.assertIn("Saved evaluation report: .cwiki/eval/wiki-eval-", result.stderr)
            reports = list((root / ".cwiki" / "eval").glob("wiki-eval-*.json"))
            self.assertEqual(len(reports), 1)

    def test_eval_llm_assisted_skips_without_configured_key(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Eval llm test")

            result = run_cwiki(
                "eval",
                str(root),
                "--json",
                "--no-write",
                "--llm",
                "--provider",
                "glm",
                "--model",
                "test-eval-model",
                "--api-key-env",
                "CWIKI_TEST_MISSING_EVAL_KEY",
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["llm_assisted"]["status"], "skipped")
            self.assertEqual(payload["llm_assisted"]["provider"], "glm")
            self.assertEqual(payload["llm_assisted"]["model"], "test-eval-model")
            self.assertIn("CWIKI_TEST_MISSING_EVAL_KEY", payload["llm_assisted"]["reason"])

    def test_eval_schedule_writes_local_config_and_runs_when_due(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Eval schedule test")

            result = run_cwiki(
                "eval-schedule",
                str(root),
                "--every-days",
                "3",
                "--llm",
                "--provider",
                "glm",
                "--model",
                "test-eval-model",
                "--api-key-env",
                "CWIKI_TEST_MISSING_EVAL_KEY",
            )
            self.assertIn("Saved scheduled evaluation config", result.stdout)
            config_file = root / ".cwiki" / "eval" / "schedule.json"
            config = json.loads(config_file.read_text(encoding="utf-8"))
            self.assertEqual(config["every_days"], 3)
            self.assertTrue(config["llm"])
            self.assertEqual(config["model"], "test-eval-model")

            result = run_cwiki("eval-schedule", str(root), "--run-if-due")
            self.assertIn("Saved evaluation report: .cwiki/eval/combined-eval-", result.stdout)
            config = json.loads(config_file.read_text(encoding="utf-8"))
            self.assertIsNotNone(config["last_run"])

    def test_eval_all_combines_wiki_and_answer_quality(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Combined eval test")
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

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| Retrieval finds relevant evidence before synthesis. | raw/captures/retrieval.md | high | 2026-05-10 |
""",
                encoding="utf-8",
            )
            answer = root / ".cwiki" / "answers" / "answer-good.md"
            answer.parent.mkdir(parents=True, exist_ok=True)
            answer.write_text(
                """---
title: Answer - Retrieval
tags: [answer]
sources: 1
updated: 2026-05-10
status: draft
question: What does retrieval do?
---

# Answer - Retrieval

## Question

What does retrieval do?

## Answer

Retrieval finds relevant evidence before synthesis, according to [[retrieval]] and `raw/captures/retrieval.md`.

## Gaps

The wiki does not yet compare retrieval strategies.

## Relevant Pages

- [[retrieval]] (10) `wiki/concepts/retrieval.md`
""",
                encoding="utf-8",
            )

            result = run_cwiki("eval-all", str(root), "--answer", str(answer))
            self.assertIn("# Combined Evaluation", result.stdout)
            self.assertIn("Wiki Quality:", result.stdout)
            self.assertIn("Answer Quality:", result.stdout)
            self.assertIn("Saved evaluation report: .cwiki/eval/combined-eval-", result.stdout)

            reports = list((root / ".cwiki" / "eval").glob("combined-eval-*.md"))
            self.assertEqual(len(reports), 1)
            report = reports[0].read_text(encoding="utf-8")
            self.assertIn("mode: combined", report)
            self.assertIn("llm_assisted: false", report)
            self.assertIn("answer_file: .cwiki/answers/answer-good.md", report)
            self.assertIn("### Wiki Quality Counts", report)
            self.assertIn("- Broken links: 0", report)
            self.assertIn("- Orphan pages:", report)
            self.assertIn("- Missing frontmatter pages: 0", report)
            self.assertIn("- Pages without Claim Ledger: 0", report)
            self.assertIn("- Claim rows missing source: 0", report)
            self.assertIn("- Stale pages: 0", report)
            index = (root / ".cwiki" / "eval" / "index.md").read_text(encoding="utf-8")
            self.assertIn("| combined |", index)
            self.assertIn(reports[0].name, index)

    def test_eval_all_auto_selects_latest_answer_when_answer_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Combined latest eval test")
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

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| Retrieval finds relevant evidence before synthesis. | raw/captures/retrieval.md | high | 2026-05-10 |
""",
                encoding="utf-8",
            )
            answers_dir = root / ".cwiki" / "answers"
            answers_dir.mkdir(parents=True, exist_ok=True)
            old_answer = answers_dir / "answer-2026-05-10-old.md"
            latest_answer = answers_dir / "answer-2026-05-11-latest.md"
            answer_body = """---
title: Answer - Retrieval
tags: [answer]
sources: 1
updated: 2026-05-10
status: draft
question: What does retrieval do?
---

# Answer - Retrieval

## Question

What does retrieval do?

## Answer

Retrieval finds relevant evidence before synthesis, according to [[retrieval]] and `raw/captures/retrieval.md`.

## Gaps

The wiki does not yet compare retrieval strategies.

## Relevant Pages

- [[retrieval]] (10) `wiki/concepts/retrieval.md`
"""
            old_answer.write_text(answer_body, encoding="utf-8")
            latest_answer.write_text(answer_body, encoding="utf-8")
            os.utime(old_answer, (1_700_000_000, 1_700_000_000))
            os.utime(latest_answer, (1_800_000_000, 1_800_000_000))

            result = run_cwiki("eval-all", str(root), "--json", "--no-write")
            payload = json.loads(result.stdout)
            deterministic = payload["deterministic"]
            self.assertEqual(deterministic["answer_selection"]["mode"], "latest")
            self.assertEqual(deterministic["answer_selection"]["selected"], ".cwiki/answers/answer-2026-05-11-latest.md")
            self.assertEqual(Path(deterministic["answer_file"]).resolve(), latest_answer.resolve())
            self.assertIsNotNone(deterministic["scores"]["answer_quality"])

    def test_eval_all_json_supports_wiki_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Combined eval json test")

            result = run_cwiki("eval-all", str(root), "--json", "--no-write", "--wiki-only")
            payload = json.loads(result.stdout)
            deterministic = payload["deterministic"]
            self.assertEqual(deterministic["mode"], "combined")
            self.assertEqual(deterministic["answer_selection"]["mode"], "wiki_only")
            self.assertIsNone(deterministic["answer"])
            self.assertIsNone(deterministic["scores"]["answer_quality"])
            self.assertEqual(deterministic["scores"]["overall"], deterministic["scores"]["wiki_quality"])
            self.assertFalse((root / ".cwiki" / "eval").exists())

    def test_eval_answer_counts_citations_in_answer_subsections(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Answer subsection eval test")
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
""",
                encoding="utf-8",
            )
            answer = root / "answer-subsections.md"
            answer.write_text(
                """# Answer

## Question

What does retrieval do?

## Answer

Short answer.

## Details

Retrieval finds evidence before synthesis according to [[retrieval]] and `raw/captures/retrieval.md`.

## Gaps

More comparison is needed.

## Relevant Pages

- [[retrieval]] (10) `wiki/concepts/retrieval.md`
""",
                encoding="utf-8",
            )

            result = run_cwiki("eval-answer", str(root), str(answer), "--no-write")
            self.assertIn("Wiki citations: 1", result.stdout)
            self.assertIn("Used Relevant Pages: 1", result.stdout)
            self.assertNotIn("Answer body does not use local wiki citations", result.stdout)

    def test_eval_answer_accepts_explicitly_unused_relevant_pages(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Unused relevant eval test")
            for slug in ["retrieval", "ranking"]:
                (root / "wiki" / "concepts" / f"{slug}.md").write_text(
                    f"""---
title: {slug.title()}
kind: concept
tags: [test]
sources: 1
updated: 2026-05-10
status: active
---

# {slug.title()}
""",
                    encoding="utf-8",
                )
            answer = root / "answer-unused.md"
            answer.write_text(
                """# Answer

## Question

What does retrieval do?

## Evidence Used

- [[retrieval]] - used - source: raw/captures/retrieval.md
- [[ranking]] - not used - reason: ranking is adjacent but not needed for this answer.

## Answer

Retrieval finds evidence before synthesis according to [[retrieval]] and `raw/captures/retrieval.md`.

## Gaps

[[ranking]] was not used because the question did not ask about ranking.

## Relevant Pages

- [[retrieval]] (10) `wiki/concepts/retrieval.md`
- [[ranking]] (5) `wiki/concepts/ranking.md`
""",
                encoding="utf-8",
            )

            result = run_cwiki("eval-answer", str(root), str(answer), "--no-write")
            self.assertIn("Explicitly Not Used Relevant Pages: 1", result.stdout)
            self.assertNotIn("Some Relevant Pages are not used", result.stdout)

    def test_eval_answer_flags_missing_grounding_and_bad_links(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Bad answer eval test")
            answer = root / "answer-bad.md"
            answer.write_text(
                """# Bad Answer

## Question

What does retrieval do?

## Answer

Retrieval definitely improves production accuracy by 42 percent across current deployments and should always be used for every system.

This also cites a missing page [[missing-page]].

## Relevant Pages

- [[missing-page]] (5) `wiki/concepts/missing-page.md`
""",
                encoding="utf-8",
            )

            result = run_cwiki("eval-answer", str(root), str(answer), "--no-write")
            self.assertIn("# Answer Evaluation", result.stdout)
            self.assertIn("Risk: high", result.stdout)
            self.assertIn("Answer cites a missing wiki page", result.stdout)
            self.assertIn("Fact-like paragraph", result.stdout)
            self.assertIn("Answer does not state gaps", result.stdout)
            self.assertFalse((root / ".cwiki" / "eval").exists())

    def test_eval_answer_flags_truncated_answers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Truncated answer eval test")
            (root / "wiki" / "concepts" / "retrieval.md").write_text(
                """---
title: Retrieval
kind: concept
tags: [test]
sources: 1
updated: 2026-05-10
status: active
---

# Retrieval
""",
                encoding="utf-8",
            )
            answer = root / "answer-truncated.md"
            answer.write_text(
                """# Answer

## Question

What does retrieval do?

## Answer

## Evidence Used

- [[retrieval]] - used - source: raw/captures/retrieval.md
- [[ranking

## Relevant Pages

- [[retrieval]] (10) `wiki/concepts/retrieval.md`
""",
                encoding="utf-8",
            )

            result = run_cwiki("eval-answer", str(root), str(answer), "--no-write")
            self.assertIn("Risk: high", result.stdout)
            self.assertIn("Answer body is too short", result.stdout)
            self.assertIn("unclosed wikilink", result.stdout)

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
            prompt_text = prompt.read_text(encoding="utf-8")
            self.assertIn("Preserve the source language", prompt_text)
            self.assertIn("Mandatory global pages refresh", prompt_text)
            self.assertIn("Open both `wiki/overview.md` and `wiki/synthesis.md` on every ingest", prompt_text)
            self.assertIn("status: seed", prompt_text)
            self.assertIn("What changed in `wiki/overview.md`", prompt_text)
            self.assertIn("What changed in `wiki/synthesis.md`", prompt_text)

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
            raw = raw_file.read_text(encoding="utf-8")
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
            raw = raw_file.read_text(encoding="utf-8")
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
            raw = raw_file.read_text(encoding="utf-8")
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
            raw = raw_file.read_text(encoding="utf-8")
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
            prompt_text = prompt.read_text(encoding="utf-8")
            self.assertIn("source paths or URLs", prompt_text)
            self.assertIn("## Evidence Used", prompt_text)
            self.assertIn("Always include a `## Gaps` section", prompt_text)
            self.assertIn("not used - reason", prompt_text)
            self.assertIn("hybrid agent workflow", prompt_text)
            self.assertIn("## Retrieval Trace", prompt_text)
            self.assertIn("retrieval_strategy:", prompt_text)
            brief_text = brief.read_text(encoding="utf-8")
            self.assertIn("Retrieval Trace", brief_text)

    def test_auto_path_records_direct_edge_path_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Path evidence test")
            (root / "wiki" / "concepts" / "alpha.md").write_text(
                """---
title: Alpha
kind: concept
tags: [test]
sources: 1
updated: 2026-05-10
status: active
---

# Alpha

Alpha relates to [[beta]].
""",
                encoding="utf-8",
            )
            (root / "wiki" / "concepts" / "beta.md").write_text(
                """---
title: Beta
kind: concept
tags: [test]
sources: 1
updated: 2026-05-10
status: active
---

# Beta

Beta is the paired concept for alpha.
""",
                encoding="utf-8",
            )

            run_cwiki("ask", str(root), "How does alpha relate to beta?", "--retrieval", "auto")
            prompt = next((root / ".cwiki" / "prompts").glob("query-*-how-does-alpha-relate-to-beta.md"))
            prompt_text = prompt.read_text(encoding="utf-8")
            self.assertIn("retrieval_strategy: path", prompt_text)
            self.assertIn("retrieval_path_count: 1", prompt_text)
            self.assertIn("- [[alpha]] -> [[beta]]", prompt_text)

    def test_auto_path_without_path_evidence_falls_back_to_graph(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Fallback test")
            for slug in ["alpha", "beta"]:
                (root / "wiki" / "concepts" / f"{slug}.md").write_text(
                    f"""---
title: {slug.title()}
kind: concept
tags: [test]
sources: 1
updated: 2026-05-10
status: active
---

# {slug.title()}

{slug.title()} is a standalone concept.
""",
                    encoding="utf-8",
                )

            run_cwiki("ask", str(root), "How does alpha relate to beta?", "--retrieval", "auto")
            prompt = next((root / ".cwiki" / "prompts").glob("query-*-how-does-alpha-relate-to-beta.md"))
            prompt_text = prompt.read_text(encoding="utf-8")
            self.assertIn("retrieval_strategy: graph", prompt_text)
            self.assertIn("retrieval_requested: auto", prompt_text)
            self.assertIn("retrieval_path_count: 0", prompt_text)
            self.assertIn("retrieval_fallback_from: path", prompt_text)
            self.assertIn("fell back to graph retrieval", prompt_text)

    def test_eval_answer_reports_retrieval_quality_from_query_prompt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Retrieval quality test")
            (root / "wiki" / "concepts" / "retrieval.md").write_text(
                """---
title: Retrieval
kind: concept
tags: [rag]
sources: 1
updated: 2026-05-10
status: active
---

# Retrieval

Retrieval links evidence to [[synthesis]] and supports [[reranking]].

## Claim Ledger

| Claim | Source | Confidence | Last checked |
|---|---|---:|---|
| Retrieval links evidence to synthesis. | raw/captures/retrieval.md | high | 2026-05-10 |
""",
                encoding="utf-8",
            )
            (root / "wiki" / "concepts" / "reranking.md").write_text(
                """---
title: Reranking
kind: concept
tags: [rag]
sources: 1
updated: 2026-05-10
status: active
---

# Reranking

Reranking depends on [[retrieval]].
""",
                encoding="utf-8",
            )

            run_cwiki("ask", str(root), "How does reranking relate to synthesis?", "--retrieval", "path")
            prompt = next((root / ".cwiki" / "prompts").glob("query-*-how-does-reranking-relate-to-synthesis.md"))
            prompt_text = prompt.read_text(encoding="utf-8")
            self.assertIn("retrieval_strategy: path", prompt_text)
            self.assertIn("## Retrieval Trace", prompt_text)

            answer = root / ".cwiki" / "answers" / "answer-retrieval-quality.md"
            answer.parent.mkdir(parents=True, exist_ok=True)
            answer.write_text(
                f"""# Answer - Retrieval Quality

## Question

How does reranking relate to synthesis?

## Answer

Reranking depends on [[retrieval]], and retrieval connects evidence to [[synthesis]] according to `raw/captures/retrieval.md`.

## Gaps

The wiki does not yet compare reranking algorithms.

## Relevant Pages

- [[reranking]] (10) `wiki/concepts/reranking.md`
- [[retrieval]] (8) `wiki/concepts/retrieval.md`
- [[synthesis]] (3) `wiki/synthesis.md`

## Query Prompt

`{prompt.relative_to(root).as_posix()}`
""",
                encoding="utf-8",
            )

            result = run_cwiki("eval-answer", str(root), str(answer), "--no-write")
            self.assertIn("Retrieval Quality:", result.stdout)
            self.assertIn("Strategy used: path", result.stdout)
            self.assertIn("Direct hit usage:", result.stdout)

    def test_eval_answer_lists_graph_and_path_retrieval_details(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Retrieval detail test")
            (root / "wiki" / "concepts" / "retrieval.md").write_text(
                """---
title: Retrieval
kind: concept
tags: [rag]
sources: 1
updated: 2026-05-10
status: active
---

# Retrieval

Retrieval connects to [[ranking]].
""",
                encoding="utf-8",
            )
            (root / "wiki" / "concepts" / "ranking.md").write_text(
                """---
title: Ranking
kind: concept
tags: [rag]
sources: 1
updated: 2026-05-10
status: active
---

# Ranking

Ranking orders retrieved pages.
""",
                encoding="utf-8",
            )
            prompt = root / ".cwiki" / "prompts" / "query-retrieval-details.md"
            prompt.write_text(
                """---
title: Query Prompt - Retrieval details
tags: [query, prompt]
sources: 2
updated: 2026-05-10
status: pending
retrieval_strategy: graph
retrieval_requested: graph
retrieval_complexity: low
retrieval_direct_hits: 1
retrieval_graph_expanded: 1
retrieval_path_count: 1
---

# Query Prompt - Retrieval details

## Retrieval Trace

- Requested strategy: graph
- Strategy used: graph
- Complexity: low
- Direct hit count: 1
- Graph-expanded page count: 1
- Path evidence count: 1

### Direct Hits

- [[retrieval]] (10) `wiki/concepts/retrieval.md`

### Graph-Expanded Pages

- [[ranking]] (7) `wiki/concepts/ranking.md` - outbound neighbor of [[retrieval]]

### Path Evidence

- [[retrieval]] -> [[ranking]]

### Final Context Pages

- [[retrieval]] (10) `wiki/concepts/retrieval.md`
- [[ranking]] (7) `wiki/concepts/ranking.md`
""",
                encoding="utf-8",
            )
            answer = root / ".cwiki" / "answers" / "answer-retrieval-details.md"
            answer.parent.mkdir(parents=True, exist_ok=True)
            answer.write_text(
                f"""# Answer - Retrieval Details

## Question

How does retrieval use ranking?

## Answer

Retrieval uses [[ranking]] to order candidate pages according to [[retrieval]] and `raw/captures/retrieval.md`.

## Gaps

The wiki does not compare ranking algorithms.

## Relevant Pages

- [[retrieval]] (10) `wiki/concepts/retrieval.md`
- [[ranking]] (7) `wiki/concepts/ranking.md`

## Query Prompt

`{prompt.relative_to(root).as_posix()}`
""",
                encoding="utf-8",
            )

            result = run_cwiki("eval-answer", str(root), str(answer), "--no-write")
            self.assertIn("Graph-Expanded Pages Detail", result.stdout)
            self.assertIn("[[ranking]] (7) `wiki/concepts/ranking.md` - outbound neighbor of [[retrieval]] - used in answer", result.stdout)
            self.assertIn("Path Evidence Detail", result.stdout)
            self.assertIn("[[retrieval]] -> [[ranking]]", result.stdout)

    def test_llm_eval_prompt_follows_report_language(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Language test")
            result = {
                "mode": "answer",
                "target": root.as_posix(),
                "language": "zh-CN",
                "scores": {"overall": 90},
                "counts": {"warnings": 1},
                "warnings": [],
            }

            prompt = CWIKI.build_llm_eval_prompt(root, result)
            instruction = CWIKI.llm_eval_language_instruction("zh-CN")
            self.assertIn("Required response language: Simplified Chinese (zh-CN)", prompt)
            self.assertIn("Use the required response language", prompt)
            self.assertIn("Respond entirely in Simplified Chinese", instruction)
            self.assertIn("摘要", instruction)
            self.assertIn("优先修复", instruction)

    def test_eval_answer_attaches_agent_platform_llm_evaluation_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
            root = Path(tmp)
            run_cwiki("init", str(root), "--domain", "Agent eval attach test")
            (root / "wiki" / "concepts" / "retrieval.md").write_text(
                """---
title: Retrieval
kind: concept
tags: [rag]
sources: 1
updated: 2026-05-10
status: active
---

# Retrieval

Retrieval finds evidence before synthesis.
""",
                encoding="utf-8",
            )
            answer = root / ".cwiki" / "answers" / "answer-agent-eval.md"
            answer.parent.mkdir(parents=True, exist_ok=True)
            answer.write_text(
                """# Answer

## Question

What does retrieval do?

## Answer

Retrieval finds evidence before synthesis according to [[retrieval]] and `raw/captures/retrieval.md`.

## Gaps

No known gaps from the inspected wiki context.

## Relevant Pages

- [[retrieval]] (10) `wiki/concepts/retrieval.md`
""",
                encoding="utf-8",
            )
            agent_eval = root / ".cwiki" / "eval" / "agent-assisted-eval.md"
            agent_eval.parent.mkdir(parents=True, exist_ok=True)
            agent_eval.write_text("# 摘要\n\n当前 agent 模型认为答案证据充足。\n\n# 优先修复\n\n- 暂无。", encoding="utf-8")

            result = run_cwiki(
                "eval-answer",
                str(root),
                str(answer),
                "--no-write",
                "--agent-eval-file",
                agent_eval.relative_to(root).as_posix(),
                "--agent-model",
                "codex-current",
            )

            self.assertIn("llm_assisted: true", result.stdout)
            self.assertIn("llm_provider: agent-platform", result.stdout)
            self.assertIn("llm_model: codex-current", result.stdout)
            self.assertIn("Provider: `agent-platform`", result.stdout)
            self.assertIn("Model: `codex-current`", result.stdout)
            self.assertIn("Source file: `.cwiki/eval/agent-assisted-eval.md`", result.stdout)
            self.assertIn("当前 agent 模型认为答案证据充足", result.stdout)

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
            prompt_text = prompt.read_text(encoding="utf-8")
            self.assertIn("wiki-agent-browser", prompt_text)
            self.assertIn("Search the web for up to 4 high-quality sources", prompt_text)
            self.assertIn("Do not cite search result snippets", prompt_text)
            self.assertIn("For every external factual claim, cite a URL", prompt_text)
            self.assertIn("Local wiki weight: 0.7", prompt_text)
            self.assertIn("Web search weight: 0.3", prompt_text)
            self.assertIn("web_mode: enabled", research.read_text(encoding="utf-8"))
            self.assertIn("Evidence Fusion Prompt", fusion.read_text(encoding="utf-8"))

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
            self.assertIn("Web mode: disabled", prompt.read_text(encoding="utf-8"))
            self.assertIn("Search the web for up to 0 high-quality sources", prompt.read_text(encoding="utf-8"))
            self.assertIn("web_mode: disabled", research.read_text(encoding="utf-8"))

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
            text = prompt.read_text(encoding="utf-8")
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
            text = brief.read_text(encoding="utf-8")
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

    def test_answer_warns_when_model_output_looks_truncated(self) -> None:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = {
                    "choices": [
                        {
                            "message": {
                                "content": "## Evidence Used\n- [[retrieval]] - used - source: raw/captures/retrieval.md\n- [[ranking"
                            }
                        }
                    ]
                }
                data = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        old_key = os.environ.get("CWIKI_TEST_GLM_KEY")
        os.environ["CWIKI_TEST_GLM_KEY"] = "test-key"
        try:
            with tempfile.TemporaryDirectory(prefix="cwiki-") as tmp:
                root = Path(tmp)
                run_cwiki("init", str(root), "--domain", "Truncated answer health test")
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
                    "--provider",
                    "glm",
                    "--api-key-env",
                    "CWIKI_TEST_GLM_KEY",
                    "--base-url",
                    f"http://127.0.0.1:{server.server_port}/v1",
                    check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("Saved answer:", result.stdout)
                self.assertIn("Answer may be truncated; please retry.", result.stderr)
                self.assertIn("Unclosed wikilink", result.stderr)
                self.assertIn("Missing required `## Answer` section", result.stderr)
                answers = list((root / ".cwiki" / "answers").glob("answer-*.md"))
                self.assertEqual(len(answers), 1)
                answer_text = answers[0].read_text(encoding="utf-8")
                self.assertIn("status: suspicious", answer_text)
                self.assertIn("answer_health: failed", answer_text)
                self.assertIn("health_warnings:", answer_text)
                self.assertIn("## Answer Health", answer_text)
                self.assertIn("This answer may be truncated or malformed", answer_text)
        finally:
            if old_key is None:
                os.environ.pop("CWIKI_TEST_GLM_KEY", None)
            else:
                os.environ["CWIKI_TEST_GLM_KEY"] = old_key
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
