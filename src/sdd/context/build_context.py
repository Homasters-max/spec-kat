"""Staged context builder — Spec_v2 §4.8."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from sdd.core.errors import MissingContext
from sdd.domain.state.yaml_state import read_state
from sdd.domain.tasks.parser import Task, parse_taskset
from sdd.infra import paths as _paths


class ContextDepth:
    COMPACT = "COMPACT"
    STANDARD = "STANDARD"
    VERBOSE = "VERBOSE"


TOKEN_BUDGET: dict[str, int] = {
    ContextDepth.COMPACT: 2_000,
    ContextDepth.STANDARD: 6_000,
    ContextDepth.VERBOSE: 12_000,
}

_BUDGET_SAFETY_FACTOR: float = 0.75
EFFECTIVE_BUDGET: dict[str, int] = {
    k: int(v * _BUDGET_SAFETY_FACTOR) for k, v in TOKEN_BUDGET.items()
}


def build_context(
    agent_type: str,
    task_id: str | None,
    depth: str,
    config: dict[str, Any],
) -> str:
    """Staged context loader (SEM-9). Returns markdown string.

    Pure: no I/O beyond reads. Layers appended 0→8 (I-CTX-6). Budget: EFFECTIVE_BUDGET[depth].
    First line: <!-- context_hash: <sha256> --> (I-CTX-5).
    """
    ctx = config.get("context", {})
    _state_yaml: str = ctx.get("state_path") or str(_paths.state_file())
    _phases_md: str = ctx.get("phases_index_path") or str(_paths.phases_index_file())
    specs_dir = Path(ctx.get("specs_dir") or str(_paths.specs_dir()))
    plans_dir = Path(ctx.get("plans_dir") or str(_paths.plans_dir()))
    tasks_dir = Path(ctx.get("tasks_dir") or str(_paths.tasks_dir()))

    loaded: dict[str, str] = {}

    def _read(path: str | Path) -> str:
        key = str(path)
        if key not in loaded:
            p = Path(path)
            if not p.exists():
                raise MissingContext(f"Required file not found: {key}")
            loaded[key] = p.read_text(encoding="utf-8")
        return loaded[key]

    # Read state to determine current phase
    _read(_state_yaml)
    state = read_state(_state_yaml)
    phase_n = state.phase_current

    # Resolve canonical artifact paths
    spec_candidates = sorted(specs_dir.glob(f"Spec_v{phase_n}_*.md"))
    if not spec_candidates:
        raise MissingContext(f"No Spec_v{phase_n}_*.md found in {specs_dir}")
    spec_path = spec_candidates[0]
    plan_path = plans_dir / f"Plan_v{phase_n}.md"
    taskset_path = tasks_dir / f"TaskSet_v{phase_n}.md"

    # Resolve task for coder agents
    task: Task | None = None
    if agent_type == "coder" and task_id is not None:
        _read(str(taskset_path))  # track in loaded for hash
        all_tasks = parse_taskset(str(taskset_path))
        for t in all_tasks:
            if t.task_id == task_id:
                task = t
                break
        if task is None:
            raise MissingContext(f"Task {task_id} not found in {taskset_path}")

    is_coder = agent_type == "coder"
    is_std_or_verbose = depth in (ContextDepth.STANDARD, ContextDepth.VERBOSE)
    is_verbose = depth == ContextDepth.VERBOSE

    # Reserve header words from budget so total output stays within EFFECTIVE_BUDGET
    placeholder_hash = "0" * 64
    meta_header = (
        f"<!-- context_hash: {placeholder_hash} -->\n"
        f"<!-- agent_type: {agent_type}, depth: {depth} -->\n"
    )
    budget_left = EFFECTIVE_BUDGET[depth] - len(meta_header.split())

    # Build layer list in strict ascending index order (I-CTX-6)
    layers: list[tuple[int, str]] = []

    # Layer 0: domain glossary (all agent types, all depths)
    glossary: dict[str, Any] = config.get("domain", {}).get("glossary", {})
    if glossary:
        gl = "\n".join(f"- **{k}**: {v}" for k, v in sorted(glossary.items()))
        layers.append((0, f"## Domain Glossary\n\n{gl}\n"))
    else:
        layers.append((0, "## Domain Glossary\n\n(empty)\n"))

    # Layer 1: state summary (all)
    layers.append((1, f"## State Summary\n\n```yaml\n{_read(_state_yaml)}```\n"))

    # Layer 2: phases index (all)
    layers.append((2, f"## Phases Index\n\n{_read(_phases_md)}\n"))

    # Layer 3: single task row — coder only (I-CTX-3)
    if is_coder and task is not None:
        layers.append((3, f"## Task Row\n\n{_format_task_row(task)}\n"))

    # Layer 4: spec section (STANDARD+)
    if is_std_or_verbose:
        spec_content = _read(str(spec_path))
        if is_coder and task is not None and task.spec_section:
            section = _extract_section(spec_content, task.spec_section)
        else:
            section = _spec_overview(spec_content)
        layers.append((4, f"## Spec Section\n\n{section}\n"))

    # Layer 5: plan milestone (STANDARD+)
    if is_std_or_verbose:
        plan_content = _read(str(plan_path))
        milestone = _extract_milestone(plan_content, task_id)
        layers.append((5, f"## Plan Milestone\n\n{milestone}\n"))

    # Layer 6: full spec (VERBOSE)
    if is_verbose:
        layers.append((6, f"## Full Spec\n\n{_read(str(spec_path))}\n"))

    # Layer 7: full plan (VERBOSE)
    if is_verbose:
        layers.append((7, f"## Full Plan\n\n{_read(str(plan_path))}\n"))

    # Layer 8: task input file contents — coder VERBOSE only (I-CTX-3)
    if is_coder and is_verbose and task is not None:
        parts: list[str] = []
        for inp in task.inputs:
            try:
                parts.append(f"### {inp}\n\n```\n{_read(inp)}```\n")
            except MissingContext:
                parts.append(f"### {inp}\n\n(file not found)\n")
        layers.append((8, f"## Input Files\n\n{''.join(parts)}\n"))

    # Apply budget — truncate at paragraph boundary when exhausted (I-CTX-2, I-CTX-6)
    body_parts: list[str] = []
    for _, content in layers:
        if budget_left <= 0:
            break
        wc = len(content.split())
        if wc <= budget_left:
            body_parts.append(content)
            budget_left -= wc
        else:
            truncated = _truncate_at_paragraph(content, budget_left)
            if truncated:
                body_parts.append(truncated)
            budget_left = 0
            break

    # Compute context_hash: covers agent_type, task_id, depth, and all loaded file hashes
    file_hashes = {
        p: hashlib.sha256(c.encode("utf-8")).hexdigest()
        for p, c in sorted(loaded.items())
    }
    hash_data = json.dumps(
        {
            "agent_type": agent_type,
            "task_id": task_id,
            "depth": depth,
            "files": file_hashes,
        },
        sort_keys=True,
    )
    context_hash = hashlib.sha256(hash_data.encode("utf-8")).hexdigest()

    header = (
        f"<!-- context_hash: {context_hash} -->\n"
        f"<!-- agent_type: {agent_type}, depth: {depth} -->\n"
    )
    return header + "\n".join(body_parts)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _format_task_row(task: Task) -> str:
    """Serialise a Task back to TaskSet-compatible markdown (parseable by parse_taskset)."""
    lines: list[str] = [f"## {task.task_id}: {task.title}", ""]
    lines.append(f"Status:               {task.status}")
    lines.append(f"Spec ref:             {task.spec_section}")
    if task.inputs:
        lines.append(f"Inputs:               {', '.join(task.inputs)}")
    if task.outputs:
        lines.append(f"Outputs:              {', '.join(task.outputs)}")
    if task.checks:
        lines.append(f"Checks:               {', '.join(task.checks)}")
    if task.spec_refs:
        lines.append(f"spec_refs:            {', '.join(task.spec_refs)}")
    if task.produces_invariants:
        lines.append(f"produces_invariants:  {', '.join(task.produces_invariants)}")
    if task.requires_invariants:
        lines.append(f"requires_invariants:  {', '.join(task.requires_invariants)}")
    lines.append("---")
    return "\n".join(lines)


def _extract_section(spec_content: str, spec_ref: str) -> str:
    """Extract spec section matching the first §N.M reference in spec_ref."""
    refs = re.findall(r"§([\d.]+)", spec_ref)
    if not refs:
        return spec_content
    section_num = refs[0]
    lines = spec_content.splitlines()
    start_idx: int | None = None
    heading_level = 0
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+" + re.escape(section_num) + r"[.\s]", line)
        if m:
            start_idx = i
            heading_level = len(m.group(1))
            break
    if start_idx is None:
        return spec_content
    end_pattern = r"^#{1," + str(heading_level) + r"}\s+\S"
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if re.match(end_pattern, lines[i]):
            end_idx = i
            break
    return "\n".join(lines[start_idx:end_idx])


def _spec_overview(spec_content: str) -> str:
    """Return spec preamble (content before the first ## section heading)."""
    lines = spec_content.splitlines()
    end_idx = len(lines)
    for i, line in enumerate(lines):
        if i > 0 and re.match(r"^#{2}\s+", line):
            end_idx = i
            break
    return "\n".join(lines[:end_idx])


def _extract_milestone(plan_content: str, task_id: str | None) -> str:
    """Extract plan milestone section for task_id via milestone mapping comment."""
    if task_id is None:
        return plan_content
    m_tid = re.match(r"T-(\d+)", task_id)
    if not m_tid:
        return plan_content
    tid_num = int(m_tid.group(1))
    lines = plan_content.splitlines()
    milestone_label: str | None = None
    for line in lines:
        if "Milestone mapping:" in line:
            for seg in re.findall(r"T-(\d+)\.\.T-(\d+)\s*[→>]\s*(M\d+)", line):
                start_s, end_s, label = seg
                if int(start_s) <= tid_num <= int(end_s):
                    milestone_label = label
                    break
            break
    if milestone_label is None:
        return plan_content
    start_idx: int | None = None
    for i, line in enumerate(lines):
        if re.match(r"^###\s+" + re.escape(milestone_label) + r"[:\s]", line):
            start_idx = i
            break
    if start_idx is None:
        return plan_content
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if re.match(r"^###\s+M\d+", lines[i]):
            end_idx = i
            break
    return "\n".join(lines[start_idx:end_idx])


def _truncate_at_paragraph(content: str, budget: int) -> str:
    """Truncate content at the last complete paragraph boundary within budget words."""
    if budget <= 0:
        return ""
    paragraphs = content.split("\n\n")
    result: list[str] = []
    words_used = 0
    for para in paragraphs:
        pw = len(para.split())
        if words_used + pw <= budget:
            result.append(para)
            words_used += pw
        else:
            break
    return "\n\n".join(result)


# ─── CLI entry point (Pattern B target) ──────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI: build_context.py --agent coder|planner --task T-NNN --depth COMPACT|STANDARD|VERBOSE"""
    import argparse
    import sys

    args_list = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="build_context.py",
        description="Build staged context for a coder or planner agent (SEM-9).",
    )
    parser.add_argument("--agent", required=True, choices=["coder", "planner"])
    parser.add_argument("--task", default=None, help="Task ID (e.g. T-801)")
    parser.add_argument("--depth", default="STANDARD",
                        choices=["COMPACT", "STANDARD", "VERBOSE"])
    parser.add_argument("--profile", default=None,
                        help="Path to project_profile.yaml")
    parser.add_argument("--phase-config", default=None,
                        help="Path to phase_N.yaml override (optional)")
    ns = parser.parse_args(args_list)

    try:
        from sdd.infra.config_loader import load_config
        profile = ns.profile if ns.profile is not None else str(_paths.config_file())
        config = load_config(profile, ns.phase_config)
        output = build_context(ns.agent, ns.task, ns.depth, config)
        print(output)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
