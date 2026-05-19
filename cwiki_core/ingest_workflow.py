from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


INGEST_STEPS = ["status", "ingest-plan", "apply", "validate", "index", "link-graph", "eval"]
STEP_STATUSES = {"pending", "in_progress", "completed", "blocked"}
STEP_DESCRIPTIONS = {
    "status": "Confirm the wiki state, source, and latest ingest prompt.",
    "ingest-plan": "Create a recoverable plan for this ingest run.",
    "apply": "Use the ingest prompt to update source-backed wiki pages.",
    "validate": "Check schema, source citations, overview, and synthesis updates.",
    "index": "Run cwiki index to refresh wiki/index.md.",
    "link-graph": "Run cwiki link-graph-report to refresh wikilink navigation artifacts.",
    "eval": "Run cwiki eval or related quality checks.",
}


class IngestWorkflowError(RuntimeError):
    """Raised when an ingest workflow cannot be resolved or updated."""


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def timestamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    stripped = re.sub(r"https?://", "", stripped.lower())
    stripped = re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", "-", stripped)
    stripped = stripped.strip("-")[:64]
    return stripped or "manual"


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def ingest_runs_dir(root: Path) -> Path:
    return root / ".cwiki" / "ingest-runs"


def latest_ingest_prompt(root: Path) -> Path | None:
    prompts_dir = root / ".cwiki" / "prompts"
    if not prompts_dir.exists():
        return None
    prompts = sorted(
        prompts_dir.glob("ingest-*.md"),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    return prompts[0] if prompts else None


def latest_ingest_run_file(root: Path) -> Path | None:
    runs_dir = ingest_runs_dir(root)
    if not runs_dir.exists():
        return None
    files = sorted(
        runs_dir.glob("ingest-run-*.json"),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    return files[0] if files else None


def resolve_prompt_path(root: Path, prompt: str | None) -> Path | None:
    if not prompt:
        return latest_ingest_prompt(root)
    path = Path(prompt)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        raise IngestWorkflowError(f"Ingest prompt not found: {prompt}")
    return path


def resolve_run_file(root: Path, run: str | None = None) -> Path:
    if not run:
        latest = latest_ingest_run_file(root)
        if not latest:
            raise IngestWorkflowError("No ingest runs found. Create one with `cwiki ingest-plan <dir>`.")
        return latest

    path = Path(run)
    candidates: list[Path] = []
    if path.is_absolute() or path.exists():
        candidates.append(path)
    candidates.append(ingest_runs_dir(root) / run)
    if not run.endswith(".json"):
        candidates.append(ingest_runs_dir(root) / f"{run}.json")
        candidates.append(ingest_runs_dir(root) / f"ingest-run-{run}.json")

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise IngestWorkflowError(f"Ingest run not found: {run}")


def initial_steps(now: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for name in INGEST_STEPS:
        status = "completed" if name in {"status", "ingest-plan"} else "pending"
        steps.append(
            {
                "name": name,
                "status": status,
                "description": STEP_DESCRIPTIONS[name],
                "updated_at": now,
                "notes": [],
            }
        )
    return steps


def current_step(steps: list[dict[str, Any]]) -> str:
    for step in steps:
        if step.get("status") in {"pending", "in_progress", "blocked"}:
            return str(step.get("name", "unknown"))
    return "done"


def render_run_markdown(run: dict[str, Any]) -> str:
    artifacts = run.get("artifacts", {}) if isinstance(run.get("artifacts"), dict) else {}
    steps = run.get("steps", []) if isinstance(run.get("steps"), list) else []
    rows = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        notes = step.get("notes", [])
        note_text = "; ".join(str(note) for note in notes) if isinstance(notes, list) and notes else "-"
        rows.append(
            "| {name} | {status} | {description} | {updated} | {notes} |".format(
                name=step.get("name", "-"),
                status=step.get("status", "-"),
                description=str(step.get("description", "-")).replace("|", "\\|"),
                updated=step.get("updated_at", "-"),
                notes=note_text.replace("|", "\\|"),
            )
        )
    step_table = "\n".join(rows)
    return f"""# Ingest Run - {run.get('id')}

## State

- Current step: `{run.get('current_step')}`
- Created: {run.get('created_at')}
- Updated: {run.get('updated_at')}
- Source: `{run.get('source') or '-'}`
- Ingest prompt: `{run.get('prompt') or '-'}`

## Steps

| Step | Status | Description | Updated | Notes |
|---|---|---|---|---|
{step_table}

## Recovery Commands

```bash
cwiki ingest-status . {run.get('id')}
cwiki ingest-step . {run.get('id')} apply --status in_progress
cwiki ingest-step . {run.get('id')} apply --status completed --note "wiki pages updated"
cwiki index .
cwiki link-graph-report .
cwiki eval .
```

## Artifacts

- Run JSON: `{artifacts.get('run_json', '-')}`
- Run Markdown: `{artifacts.get('run_markdown', '-')}`
- Source: `{artifacts.get('source', '-')}`
- Prompt: `{artifacts.get('prompt', '-')}`
"""


def write_run(root: Path, run: dict[str, Any]) -> tuple[Path, Path]:
    runs_dir = ingest_runs_dir(root)
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(run["id"])
    json_file = runs_dir / f"{run_id}.json"
    markdown_file = runs_dir / f"{run_id}.md"
    run.setdefault("artifacts", {})
    run["artifacts"]["run_json"] = display_path(json_file, root)
    run["artifacts"]["run_markdown"] = display_path(markdown_file, root)
    json_file.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_file.write_text(render_run_markdown(run), encoding="utf-8")
    return json_file, markdown_file


def create_ingest_run(
    root: Path,
    source: str | None = None,
    prompt: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    prompt_path = resolve_prompt_path(root, prompt)
    seed = source or (prompt_path.stem if prompt_path else "manual")
    resolved_run_id = run_id or f"ingest-run-{timestamp()}-{slugify(seed)}"
    if not resolved_run_id.startswith("ingest-run-"):
        resolved_run_id = f"ingest-run-{slugify(resolved_run_id)}"
    now = now_iso()
    run: dict[str, Any] = {
        "schema_version": 1,
        "id": resolved_run_id,
        "created_at": now,
        "updated_at": now,
        "source": source or "",
        "prompt": display_path(prompt_path, root) if prompt_path else "",
        "current_step": "apply",
        "steps": initial_steps(now),
        "artifacts": {
            "source": source or "",
            "prompt": display_path(prompt_path, root) if prompt_path else "",
        },
    }
    write_run(root, run)
    return run


def load_run(root: Path, run: str | None = None) -> tuple[dict[str, Any], Path]:
    run_file = resolve_run_file(root.resolve(), run)
    try:
        payload = json.loads(run_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise IngestWorkflowError(f"Invalid ingest run JSON: {display_path(run_file, root)}") from error
    if not isinstance(payload, dict):
        raise IngestWorkflowError(f"Invalid ingest run payload: {display_path(run_file, root)}")
    return payload, run_file


def format_no_runs_status(root: Path) -> str:
    prompt = latest_ingest_prompt(root)
    prompt_line = f"- Latest ingest prompt: `{display_path(prompt, root)}`" if prompt else "- Latest ingest prompt: none"
    return f"""# Ingest Status

No ingest runs exist yet.

{prompt_line}

Create one with:

```bash
cwiki ingest-plan . --prompt <prompt-file>
```

Pipeline: `status -> ingest-plan -> apply -> validate -> index -> link-graph -> eval`
"""


def format_ingest_status(root: Path, run: str | None = None) -> str:
    root = root.resolve()
    try:
        payload, _run_file = load_run(root, run)
    except IngestWorkflowError:
        if run:
            raise
        return format_no_runs_status(root)
    return render_run_markdown(payload)


def update_ingest_step(
    root: Path,
    run: str | None,
    step_name: str,
    status: str,
    note: str | None = None,
) -> dict[str, Any]:
    if step_name not in INGEST_STEPS:
        raise IngestWorkflowError(f"Unknown ingest step: {step_name}. Choices: {', '.join(INGEST_STEPS)}")
    if status not in STEP_STATUSES:
        raise IngestWorkflowError(f"Unknown step status: {status}. Choices: {', '.join(sorted(STEP_STATUSES))}")

    payload, _run_file = load_run(root.resolve(), run)
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise IngestWorkflowError("Ingest run is missing a steps list.")

    now = now_iso()
    updated = False
    for step in steps:
        if isinstance(step, dict) and step.get("name") == step_name:
            step["status"] = status
            step["updated_at"] = now
            if note:
                notes = step.setdefault("notes", [])
                if isinstance(notes, list):
                    notes.append(note)
                else:
                    step["notes"] = [note]
            updated = True
            break
    if not updated:
        raise IngestWorkflowError(f"Ingest step missing from run: {step_name}")

    payload["updated_at"] = now
    payload["current_step"] = current_step([step for step in steps if isinstance(step, dict)])
    write_run(root.resolve(), payload)
    return payload
