"""SpatialIndex: deterministic map of the system (BC-18-1, Spec_v18 §3)."""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone

import yaml

from sdd.spatial.nodes import SpatialNode


@dataclass
class SpatialIndex:
    nodes:         dict[str, SpatialNode]
    built_at:      str
    git_tree_hash: str | None
    version:       int = 1
    meta:          dict = field(default_factory=dict)


class IndexBuilder:
    def __init__(self, project_root: str) -> None:
        self._root = os.path.abspath(project_root)
        self._now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> SpatialIndex:
        all_nodes: list[SpatialNode] = []
        all_nodes += self._build_file_nodes()
        all_nodes += self._build_command_nodes()
        all_nodes += self._build_guard_nodes()
        all_nodes += self._build_reducer_nodes()
        all_nodes += self._build_event_nodes()
        all_nodes += self._build_task_nodes()
        all_nodes += self._build_invariant_nodes()
        all_nodes += self._build_term_nodes()

        # I-SI-1: unique node_ids
        nodes: dict[str, SpatialNode] = {}
        for node in all_nodes:
            if node.node_id in nodes:
                raise ValueError(f"I-SI-1: duplicate node_id: {node.node_id!r}")
            nodes[node.node_id] = node

        git_tree_hash = self._git_tree_hash()
        meta = self._validate_term_links(nodes)

        return SpatialIndex(
            nodes=nodes,
            built_at=self._now,
            git_tree_hash=git_tree_hash,
            meta=meta,
        )

    # ------------------------------------------------------------------
    # Node builders
    # ------------------------------------------------------------------

    def _build_file_nodes(self) -> list[SpatialNode]:
        nodes: list[SpatialNode] = []
        src_root = os.path.join(self._root, "src", "sdd")
        if not os.path.isdir(src_root):
            return nodes
        for dirpath, dirnames, filenames in os.walk(src_root):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue
                abs_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(abs_path, self._root).replace(os.sep, "/")
                node_id = f"FILE:{rel_path}"
                nodes.append(SpatialNode(
                    node_id=node_id,
                    kind="FILE",
                    label=fname,
                    path=rel_path,
                    summary=self._extract_summary(rel_path, "FILE"),
                    signature=self._extract_signature(rel_path),
                    meta={},
                    git_hash=self._blob_hash(rel_path),
                    indexed_at=self._now,
                ))
        return nodes

    def _build_command_nodes(self) -> list[SpatialNode]:
        nodes: list[SpatialNode] = []
        registry_path = os.path.join(self._root, "src", "sdd", "commands", "registry.py")
        if not os.path.isfile(registry_path):
            return nodes
        rel_path = "src/sdd/commands/registry.py"
        git_hash = self._blob_hash(rel_path)
        try:
            with open(registry_path) as f:
                source = f.read()
            # Extract REGISTRY keys: string literals followed by ": CommandSpec("
            keys = re.findall(r'"([^"]+)"\s*:\s*CommandSpec\(', source)
            for cmd_name in sorted(set(keys)):
                node_id = f"COMMAND:{cmd_name}"
                summary = f"CLI command: sdd {cmd_name}"
                nodes.append(SpatialNode(
                    node_id=node_id,
                    kind="COMMAND",
                    label=f"sdd {cmd_name}",
                    path=rel_path,
                    summary=summary,
                    signature=f"sdd {cmd_name} [args]",
                    meta={},
                    git_hash=git_hash,
                    indexed_at=self._now,
                ))
        except Exception:
            pass
        return nodes

    def _build_guard_nodes(self) -> list[SpatialNode]:
        nodes: list[SpatialNode] = []
        guards_dir = os.path.join(self._root, "src", "sdd", "guards")
        if not os.path.isdir(guards_dir):
            return nodes
        for fname in sorted(os.listdir(guards_dir)):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            guard_name = fname[:-3]
            rel_path = f"src/sdd/guards/{fname}"
            nodes.append(SpatialNode(
                node_id=f"GUARD:{guard_name}",
                kind="GUARD",
                label=guard_name,
                path=rel_path,
                summary=self._extract_summary(rel_path, "GUARD"),
                signature=self._extract_signature(rel_path),
                meta={},
                git_hash=self._blob_hash(rel_path),
                indexed_at=self._now,
            ))
        return nodes

    def _build_reducer_nodes(self) -> list[SpatialNode]:
        rel_path = "src/sdd/domain/state/reducer.py"
        return [SpatialNode(
            node_id="REDUCER:main",
            kind="REDUCER",
            label="main reducer",
            path=rel_path,
            summary=self._extract_summary(rel_path, "REDUCER"),
            signature=self._extract_signature(rel_path),
            meta={},
            git_hash=self._blob_hash(rel_path),
            indexed_at=self._now,
        )]

    def _build_event_nodes(self) -> list[SpatialNode]:
        nodes: list[SpatialNode] = []
        rel_path = "src/sdd/core/events.py"
        abs_path = os.path.join(self._root, rel_path)
        if not os.path.isfile(abs_path):
            return nodes
        git_hash = self._blob_hash(rel_path)
        try:
            with open(abs_path) as f:
                source = f.read()
            tree = ast.parse(source)
            seen: set[str] = set()
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                if not node.name.endswith("Event"):
                    continue
                if node.name in seen:
                    continue
                seen.add(node.name)
                summary = self._class_docstring_first_line(node)
                if not summary:
                    summary = f"EVENT:{node.name}"
                nodes.append(SpatialNode(
                    node_id=f"EVENT:{node.name}",
                    kind="EVENT",
                    label=node.name,
                    path=rel_path,
                    summary=summary,
                    signature=f"class {node.name}: ...",
                    meta={},
                    git_hash=git_hash,
                    indexed_at=self._now,
                ))
        except Exception:
            pass
        return nodes

    def _build_task_nodes(self) -> list[SpatialNode]:
        nodes: list[SpatialNode] = []
        tasks_dir = os.path.join(self._root, ".sdd", "tasks")
        if not os.path.isdir(tasks_dir):
            return nodes
        taskset_files = sorted(
            f for f in os.listdir(tasks_dir)
            if f.startswith("TaskSet_v") and f.endswith(".md")
        )
        if not taskset_files:
            return nodes
        taskset_path = os.path.join(tasks_dir, taskset_files[-1])
        try:
            with open(taskset_path) as f:
                content = f.read()
            task_ids = sorted(set(re.findall(r"##\s+Task:\s+(T-\d+)", content)))
            for task_id in task_ids:
                nodes.append(SpatialNode(
                    node_id=f"TASK:{task_id}",
                    kind="TASK",
                    label=task_id,
                    path=None,
                    summary=f"TASK:{task_id}",
                    signature="",
                    meta={},
                    git_hash=None,
                    indexed_at=self._now,
                ))
        except Exception:
            pass
        return nodes

    def _build_invariant_nodes(self) -> list[SpatialNode]:
        nodes: list[SpatialNode] = []
        claude_md = os.path.join(self._root, "CLAUDE.md")
        if not os.path.isfile(claude_md):
            return nodes
        try:
            with open(claude_md) as f:
                content = f.read()
            inv_ids: list[str] = []
            seen: set[str] = set()
            for m in re.finditer(r"\|\s*(I-[A-Z][A-Z0-9\-]*(?:-\d+)?)\s*\|", content):
                inv_id = m.group(1)
                if inv_id not in seen:
                    seen.add(inv_id)
                    inv_ids.append(inv_id)
            for inv_id in inv_ids:
                nodes.append(SpatialNode(
                    node_id=f"INVARIANT:{inv_id}",
                    kind="INVARIANT",
                    label=inv_id,
                    path=None,
                    summary=f"INVARIANT:{inv_id}",
                    signature="",
                    meta={},
                    git_hash=None,
                    indexed_at=self._now,
                ))
        except Exception:
            pass
        return nodes

    def _build_term_nodes(self) -> list[SpatialNode]:
        """I-DDD-0: TERM nodes from glossary.yaml ONLY — no heuristic derivation."""
        nodes: list[SpatialNode] = []
        glossary_path = os.path.join(self._root, ".sdd", "config", "glossary.yaml")
        if not os.path.isfile(glossary_path):
            return nodes
        try:
            with open(glossary_path) as f:
                data = yaml.safe_load(f)
            for term in data.get("terms", []):
                term_id = term["id"]
                definition = term.get("definition", "")
                aliases = tuple(term.get("aliases", []))
                links = tuple(term.get("links", []))
                summary = definition.split(".")[0].strip() if definition else ""
                if not summary:
                    summary = f"TERM:{term_id}"
                signature = f"Linked: {', '.join(links)}" if links else ""
                nodes.append(SpatialNode(
                    node_id=f"TERM:{term_id}",
                    kind="TERM",
                    label=term.get("label", term_id),
                    path=None,
                    summary=summary,
                    signature=signature,
                    meta={},
                    git_hash=None,
                    indexed_at=self._now,
                    definition=definition,
                    aliases=aliases,
                    links=links,
                ))
        except Exception:
            pass
        return nodes

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_term_links(self, nodes: dict[str, SpatialNode]) -> dict:
        """I-TERM-2 + I-TERM-COVERAGE-1 post-build validation."""
        meta: dict = {}
        violations: list[dict] = []
        uncovered_commands: set[str] = {
            nid for nid in nodes if nid.startswith("COMMAND:")
        }

        for node in nodes.values():
            if node.kind != "TERM":
                continue
            for link in node.links:
                if link not in nodes:
                    kind_prefix = link.split(":")[0] if ":" in link else ""
                    # Unknown COMMAND or EVENT = error severity; others = warning
                    severity = "error" if kind_prefix in ("COMMAND", "EVENT") else "warning"
                    violations.append({
                        "term": node.node_id,
                        "missing": [link],
                        "severity": severity,
                    })
                elif link.startswith("COMMAND:"):
                    uncovered_commands.discard(link)

        if violations:
            meta["term_link_violations"] = violations
        if uncovered_commands:
            meta["term_coverage_gaps"] = sorted(uncovered_commands)
        return meta

    # ------------------------------------------------------------------
    # Source extraction utilities
    # ------------------------------------------------------------------

    def _extract_summary(self, rel_path: str, kind: str) -> str:
        """Extract 1-line summary from source file (I-SUMMARY-1, I-SUMMARY-2)."""
        abs_path = os.path.join(self._root, rel_path)
        if not os.path.isfile(abs_path):
            basename = os.path.splitext(os.path.basename(rel_path))[0]
            return f"{kind}:{basename}"
        try:
            with open(abs_path) as f:
                source = f.read()
            tree = ast.parse(source)
            # 1. Module-level docstring
            if (tree.body and isinstance(tree.body[0], ast.Expr)
                    and isinstance(tree.body[0].value, ast.Constant)
                    and isinstance(tree.body[0].value.value, str)):
                first_line = tree.body[0].value.value.strip().split("\n")[0].strip()
                if first_line:
                    return first_line
            # 2. First class/function docstring
            for stmt in ast.walk(tree):
                if isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if (stmt.body and isinstance(stmt.body[0], ast.Expr)
                            and isinstance(stmt.body[0].value, ast.Constant)
                            and isinstance(stmt.body[0].value.value, str)):
                        first_line = stmt.body[0].value.value.strip().split("\n")[0].strip()
                        if first_line:
                            return first_line
            # 3. First non-empty comment
            for line in source.split("\n"):
                stripped = line.strip()
                if stripped.startswith("#") and len(stripped) > 1:
                    comment = stripped[1:].strip()
                    if comment:
                        return comment
        except Exception:
            pass
        # 4. Fallback: I-SUMMARY-2
        basename = os.path.splitext(os.path.basename(rel_path))[0]
        return f"{kind}:{basename}"

    def _extract_signature(self, rel_path: str) -> str:
        """Extract interface-only signature (I-SIGNATURE-1): def/class declarations."""
        abs_path = os.path.join(self._root, rel_path)
        if not os.path.isfile(abs_path):
            return ""
        try:
            with open(abs_path) as f:
                source = f.read()
            tree = ast.parse(source)
            lines: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    bases = ", ".join(ast.unparse(b) for b in node.bases)
                    lines.append(f"class {node.name}({bases}): ..." if bases else f"class {node.name}: ...")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = ast.unparse(node.args)
                    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                    lines.append(f"{prefix} {node.name}({args}){ret}: ...")
            return "\n".join(lines[:15])
        except Exception:
            return ""

    def _class_docstring_first_line(self, class_node: ast.ClassDef) -> str:
        if (class_node.body and isinstance(class_node.body[0], ast.Expr)
                and isinstance(class_node.body[0].value, ast.Constant)
                and isinstance(class_node.body[0].value.value, str)):
            return class_node.body[0].value.value.strip().split("\n")[0].strip()
        return ""

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    def _git_tree_hash(self) -> str | None:
        """I-GIT-OPTIONAL: returns None if git unavailable."""
        try:
            r = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self._root, capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
        return None

    def _blob_hash(self, rel_path: str) -> str | None:
        """Get blob SHA for a tracked file via git ls-files -s (O(1))."""
        try:
            r = subprocess.run(
                ["git", "ls-files", "-s", rel_path],
                cwd=self._root, capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                parts = r.stdout.strip().split()
                if len(parts) >= 2:
                    return parts[1]
        except Exception:
            pass
        return None


# ------------------------------------------------------------------
# Module-level convenience functions
# ------------------------------------------------------------------

def build_index(project_root: str) -> SpatialIndex:
    return IndexBuilder(project_root).build()


def load_index(path: str) -> SpatialIndex:
    with open(path) as f:
        data = json.load(f)
    nodes: dict[str, SpatialNode] = {}
    for node_id, nd in data.get("nodes", {}).items():
        nodes[node_id] = SpatialNode(
            node_id=nd["node_id"],
            kind=nd["kind"],
            label=nd["label"],
            path=nd.get("path"),
            summary=nd["summary"],
            signature=nd.get("signature", ""),
            meta=nd.get("meta", {}),
            git_hash=nd.get("git_hash"),
            indexed_at=nd["indexed_at"],
            definition=nd.get("definition", ""),
            aliases=tuple(nd.get("aliases", [])),
            links=tuple(nd.get("links", [])),
        )
    return SpatialIndex(
        nodes=nodes,
        built_at=data["built_at"],
        git_tree_hash=data.get("git_tree_hash"),
        version=data.get("version", 1),
        meta=data.get("meta", {}),
    )


def save_index(index: SpatialIndex, path: str) -> None:
    nodes_dict: dict[str, dict] = {}
    for node_id, node in index.nodes.items():
        nodes_dict[node_id] = {
            "node_id": node.node_id,
            "kind": node.kind,
            "label": node.label,
            "path": node.path,
            "summary": node.summary,
            "signature": node.signature,
            "meta": node.meta,
            "git_hash": node.git_hash,
            "indexed_at": node.indexed_at,
            "definition": node.definition,
            "aliases": list(node.aliases),
            "links": list(node.links),
        }
    payload = {
        "version": index.version,
        "built_at": index.built_at,
        "git_tree_hash": index.git_tree_hash,
        "nodes": nodes_dict,
        "meta": index.meta,
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)
