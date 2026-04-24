"""I-TASK-OUTPUT-1: every DONE task must have all declared Outputs present on disk.

Scope: current active phase only (historical TaskSets are exempt — files may have
been renamed or removed in subsequent phases).

Exemptions:
  - Paths under .sdd/_deprecated_tools/ (archived, not on runtime path — I-ENV-BOOT-1a)
  - Paths that are descriptive notes (contain whitespace after stripping)
  - Paths explicitly marked "(deleted)" in any task's Outputs (intentional deletion)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent
STATE_PATH = PROJECT_ROOT / ".sdd/runtime/State_index.yaml"
DEPRECATED_PREFIX = ".sdd/_deprecated_tools"


def _current_phase() -> int:
    text = STATE_PATH.read_text(encoding="utf-8")
    state = yaml.safe_load(text)
    return int(state["phase"]["current"])


def _expand_path(raw: str) -> Path | None:
    """Expand ~ and return Path, or None if the token is not a real path."""
    raw = raw.strip()
    # Skip descriptive notes like "T-1317 result (...)" or multi-word phrases
    if " " in raw or raw.startswith("T-"):
        return None
    if not raw:
        return None
    return Path(raw).expanduser()


def _parse_done_tasks(taskset_path: Path) -> list[tuple[str, list[Path]]]:
    """Return [(task_id, [output_paths])] for every DONE task."""
    text = taskset_path.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^T-\d+[a-z]*:)", text, flags=re.MULTILINE)

    results = []
    for block in blocks:
        task_m = re.match(r"^(T-\d+[a-z]*):", block)
        if not task_m:
            continue
        task_id = task_m.group(1)

        status_m = re.search(r"^Status:\s*(\S+)", block, re.MULTILINE)
        if not status_m or status_m.group(1) != "DONE":
            continue

        outputs_m = re.search(
            r"^Outputs:\s*(.+?)(?=^\w|\Z)", block, re.MULTILINE | re.DOTALL
        )
        if not outputs_m:
            continue

        raw_outputs = outputs_m.group(1).strip()
        # Each output is comma- or newline-separated
        tokens = re.split(r"[,\n]+", raw_outputs)
        paths = []
        for tok in tokens:
            p = _expand_path(tok)
            if p is not None:
                paths.append(p)

        if paths:
            results.append((task_id, paths))

    return results


def _collect_deleted_paths(taskset_path: Path) -> set[Path]:
    """Collect paths explicitly marked deleted in the TaskSet.

    Matches:
      - "some/path (deleted..." — Outputs annotation with full path
      - bare "filename.py deleted (git rm)" — Acceptance criteria; resolved via DONE-task outputs
    """
    text = taskset_path.read_text(encoding="utf-8")
    deleted: set[Path] = set()
    deleted_basenames: set[str] = set()

    for line in text.splitlines():
        # Full-path annotation: "src/sdd/guards/pipeline.py (deleted..."
        m = re.match(r"\s*([\w./_\-]+)\s+\(deleted", line)
        if m:
            deleted.add(PROJECT_ROOT / m.group(1))
            continue
        # Basename-only: "sdd_run.py deleted (git rm)"
        m2 = re.search(r"\b([\w\-]+\.py)\s+deleted\b", line)
        if m2:
            deleted_basenames.add(m2.group(1))

    # Resolve basenames against all DONE-task declared outputs
    if deleted_basenames:
        all_outputs: set[Path] = set()
        for _task_id, paths in _parse_done_tasks(taskset_path):
            all_outputs.update(PROJECT_ROOT / p for p in paths)
        for p in all_outputs:
            if p.name in deleted_basenames:
                deleted.add(p)

    return deleted


def _is_exempt(path: Path, deleted_paths: set[Path]) -> bool:
    """Paths under .sdd/_deprecated_tools/ or marked deleted are exempt."""
    try:
        path.relative_to(PROJECT_ROOT / DEPRECATED_PREFIX)
        return True
    except ValueError:
        pass
    if str(path).startswith(DEPRECATED_PREFIX):
        return True
    return path in deleted_paths


def _collect_cases() -> list[tuple[str, Path, str]]:
    """Return (task_id, abs_path, taskset_name) for every non-exempt output in current phase."""
    phase = _current_phase()
    taskset_path = PROJECT_ROOT / f".sdd/tasks/TaskSet_v{phase}.md"
    if not taskset_path.exists():
        return []
    deleted_paths = _collect_deleted_paths(taskset_path)
    cases = []
    for task_id, paths in _parse_done_tasks(taskset_path):
        for p in paths:
            abs_p = p if p.is_absolute() else PROJECT_ROOT / p
            if not _is_exempt(abs_p, deleted_paths):
                cases.append((task_id, abs_p, taskset_path.name))
    return cases


_CASES = _collect_cases()


@pytest.mark.parametrize("task_id,abs_path,taskset", _CASES, ids=[
    f"{c[0]}:{c[1].name}" for c in _CASES
])
def test_done_task_output_exists(task_id: str, abs_path: Path, taskset: str) -> None:
    """I-TASK-OUTPUT-1: output declared in DONE task must exist on disk."""
    assert abs_path.exists(), (
        f"[{taskset}] Task {task_id} is DONE but output is missing: {abs_path}"
    )
