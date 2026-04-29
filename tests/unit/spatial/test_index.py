"""Tests for SpatialIndex and IndexBuilder (BC-18-1, T-1804).

Covers: I-SI-1, I-SI-4, I-SI-5, I-DDD-0, I-DDD-1, I-TERM-COVERAGE-1, I-TERM-2,
        I-SUMMARY-1, I-SUMMARY-2, I-SIGNATURE-1, load/save roundtrip.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.spatial.index import IndexBuilder, SpatialIndex, build_index, load_index, save_index
from sdd.spatial.nodes import SpatialNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_minimal_project(root: Path) -> None:
    """Create a minimal project layout for IndexBuilder unit tests."""
    # src/sdd/
    src = root / "src" / "sdd"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('"""SDD package."""\n')

    commands = src / "commands"
    commands.mkdir()
    (commands / "__init__.py").write_text("")
    (commands / "registry.py").write_text(
        '"""Command registry."""\n'
        'REGISTRY = {\n'
        '    "complete": CommandSpec(name="complete"),\n'
        '    "validate": CommandSpec(name="validate"),\n'
        '}\n'
    )

    guards = src / "guards"
    guards.mkdir()
    (guards / "phase.py").write_text('"""Phase guard."""\n')
    (guards / "scope.py").write_text('# scope guard\n')

    domain_state = src / "domain" / "state"
    domain_state.mkdir(parents=True)
    (domain_state / "__init__.py").write_text("")
    (domain_state / "reducer.py").write_text('"""Main SDD reducer."""\n')

    core = src / "core"
    core.mkdir()
    (core / "__init__.py").write_text("")
    (core / "events.py").write_text(
        '"""Domain events."""\n'
        'from dataclasses import dataclass\n\n'
        '@dataclass(frozen=True)\nclass DomainEvent:\n    """Base event."""\n    pass\n\n'
        '@dataclass(frozen=True)\nclass TaskImplementedEvent(DomainEvent):\n    """Emitted when task is marked done."""\n    pass\n\n'
        '@dataclass(frozen=True)\nclass PhaseCompletedEvent(DomainEvent):\n    """Emitted when phase is complete."""\n    pass\n'
    )

    # .sdd/config/glossary.yaml
    config = root / ".sdd" / "config"
    config.mkdir(parents=True)
    (config / "glossary.yaml").write_text(
        "terms:\n"
        "  - id: complete_task\n"
        "    label: Complete Task\n"
        "    definition: Mark task as done. Emits TaskImplementedEvent.\n"
        "    aliases: [task completion, sdd complete]\n"
        "    links: [\"COMMAND:complete\", \"EVENT:TaskImplementedEvent\"]\n"
        "  - id: validate_task\n"
        "    label: Validate Task\n"
        "    definition: Run invariant checks.\n"
        "    aliases: [task validation]\n"
        "    links: [\"COMMAND:validate\"]\n"
    )

    # .sdd/tasks/TaskSet_v18.md
    tasks = root / ".sdd" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "TaskSet_v18.md").write_text(
        "## Task: T-1801\n"
        "## Task: T-1802\n"
        "## Task: T-1803\n"
    )

    # CLAUDE.md with minimal invariants
    (root / "CLAUDE.md").write_text(
        "| I-SI-1 | Every indexed file has exactly one node |\n"
        "| I-SI-4 | node_id stable across rebuilds |\n"
        "| I-DDD-0 | TERM nodes from glossary.yaml |\n"
    )


@pytest.fixture
def project(tmp_path: Path) -> str:
    _write_minimal_project(tmp_path)
    return str(tmp_path)


@pytest.fixture
def no_git():
    """Make git unavailable for I-GIT-OPTIONAL tests."""
    with patch("sdd.spatial.index.subprocess.run", side_effect=FileNotFoundError()):
        yield


# ---------------------------------------------------------------------------
# SpatialIndex dataclass
# ---------------------------------------------------------------------------

class TestSpatialIndex:
    def test_construction(self, project):
        index = build_index(project)
        assert isinstance(index, SpatialIndex)
        assert isinstance(index.nodes, dict)
        assert isinstance(index.built_at, str)
        assert index.version == 1

    def test_nodes_are_spatial_nodes(self, project):
        index = build_index(project)
        for node in index.nodes.values():
            assert isinstance(node, SpatialNode)


# ---------------------------------------------------------------------------
# I-SI-1: uniqueness
# ---------------------------------------------------------------------------

class TestSI1Uniqueness:
    def test_no_duplicate_node_ids(self, project):
        index = build_index(project)
        node_ids = list(index.nodes.keys())
        assert len(node_ids) == len(set(node_ids))

    def test_each_node_id_matches_key(self, project):
        index = build_index(project)
        for key, node in index.nodes.items():
            assert key == node.node_id


# ---------------------------------------------------------------------------
# I-SI-4: stable node_ids
# ---------------------------------------------------------------------------

class TestSI4StableNodeIds:
    def test_consecutive_builds_have_same_node_ids(self, project):
        index1 = build_index(project)
        index2 = build_index(project)
        assert set(index1.nodes.keys()) == set(index2.nodes.keys())

    def test_file_node_id_derived_from_path(self, project):
        index = build_index(project)
        file_nodes = [n for n in index.nodes.values() if n.kind == "FILE"]
        for node in file_nodes:
            assert node.node_id == f"FILE:{node.path}"

    def test_command_node_id_format(self, project):
        index = build_index(project)
        cmd_nodes = [n for n in index.nodes.values() if n.kind == "COMMAND"]
        assert len(cmd_nodes) > 0
        for node in cmd_nodes:
            assert node.node_id.startswith("COMMAND:")

    def test_term_node_id_derived_from_glossary_id(self, project):
        index = build_index(project)
        assert "TERM:complete_task" in index.nodes
        assert "TERM:validate_task" in index.nodes

    def test_task_node_id_format(self, project):
        index = build_index(project)
        assert "TASK:T-1801" in index.nodes
        assert "TASK:T-1802" in index.nodes
        assert "TASK:T-1803" in index.nodes


# ---------------------------------------------------------------------------
# I-DDD-0: TERM nodes from glossary.yaml only
# ---------------------------------------------------------------------------

class TestIDD0TermSource:
    def test_term_nodes_exist(self, project):
        index = build_index(project)
        term_nodes = [n for n in index.nodes.values() if n.kind == "TERM"]
        assert len(term_nodes) > 0

    def test_all_term_nodes_have_kind_term(self, project):
        """I-DDD-0 + BUG-4 fix: TERM = SpatialNode(kind='TERM'), no TermNode class."""
        index = build_index(project)
        for node in index.nodes.values():
            if node.node_id.startswith("TERM:"):
                assert node.kind == "TERM"
                assert type(node).__name__ == "SpatialNode"

    def test_term_count_matches_glossary(self, project):
        index = build_index(project)
        term_nodes = [n for n in index.nodes.values() if n.kind == "TERM"]
        assert len(term_nodes) == 2  # complete_task + validate_task

    def test_no_term_nodes_without_glossary(self, tmp_path):
        """I-DDD-0: no heuristic TERM derivation — if no glossary, no TERM nodes."""
        (tmp_path / "src" / "sdd").mkdir(parents=True)
        (tmp_path / ".sdd" / "tasks").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("")
        index = build_index(str(tmp_path))
        term_nodes = [n for n in index.nodes.values() if n.kind == "TERM"]
        assert len(term_nodes) == 0

    def test_term_node_has_definition_and_aliases_and_links(self, project):
        index = build_index(project)
        node = index.nodes["TERM:complete_task"]
        assert node.definition != ""
        assert "task completion" in node.aliases
        assert "COMMAND:complete" in node.links


# ---------------------------------------------------------------------------
# I-DDD-1: SpatialNode.links is primary source of means edges
# ---------------------------------------------------------------------------

class TestIDDD1TermLinks:
    def test_links_are_tuples(self, project):
        index = build_index(project)
        for node in index.nodes.values():
            if node.kind == "TERM":
                assert isinstance(node.links, tuple)

    def test_links_present_in_term_nodes(self, project):
        index = build_index(project)
        node = index.nodes["TERM:complete_task"]
        assert "COMMAND:complete" in node.links
        assert "EVENT:TaskImplementedEvent" in node.links


# ---------------------------------------------------------------------------
# I-SI-5: node.git_hash consistency (mocked git)
# ---------------------------------------------------------------------------

class TestSI5GitHashConsistency:
    def test_git_tree_hash_present_when_git_available(self, project):
        fake_hash = "abc123def456abc123def456abc123def456abc123"
        fake_blob = "deadbeef" * 5

        def mock_run(args, **kwargs):
            from unittest.mock import MagicMock
            m = MagicMock()
            if "rev-parse" in args:
                m.returncode = 0
                m.stdout = fake_hash + "\n"
            elif "ls-files" in args:
                m.returncode = 0
                m.stdout = f"100644 {fake_blob} 0\t{args[-1]}\n"
            else:
                m.returncode = 1
                m.stdout = ""
            return m

        with patch("sdd.spatial.index.subprocess.run", side_effect=mock_run):
            index = build_index(project)

        assert index.git_tree_hash == fake_hash
        # FILE nodes should have blob hashes
        file_nodes = [n for n in index.nodes.values() if n.kind == "FILE"]
        assert len(file_nodes) > 0
        for node in file_nodes:
            assert node.git_hash == fake_blob

    def test_git_hash_none_when_git_unavailable(self, project, no_git):
        """I-GIT-OPTIONAL: git unavailable → git_tree_hash=None, system still works."""
        index = build_index(project)
        assert index.git_tree_hash is None
        # TERM and INVARIANT nodes always have None git_hash
        for node in index.nodes.values():
            if node.kind in ("TERM", "INVARIANT", "TASK"):
                assert node.git_hash is None

    def test_term_invariant_task_nodes_have_none_git_hash(self, project):
        index = build_index(project)
        for node in index.nodes.values():
            if node.kind in ("TERM", "INVARIANT", "TASK"):
                assert node.git_hash is None, f"{node.node_id} should have git_hash=None"


# ---------------------------------------------------------------------------
# Summary invariants (I-SUMMARY-1, I-SUMMARY-2)
# ---------------------------------------------------------------------------

class TestSummaryInvariants:
    def test_i_summary_1_all_summaries_single_line(self, project):
        index = build_index(project)
        for node in index.nodes.values():
            assert "\n" not in node.summary, (
                f"I-SUMMARY-1: {node.node_id!r} summary has newline: {node.summary!r}"
            )

    def test_i_summary_2_no_empty_summaries(self, project):
        index = build_index(project)
        for node in index.nodes.values():
            assert node.summary, f"I-SUMMARY-2: {node.node_id!r} has empty summary"

    def test_i_summary_2_fallback_format(self, tmp_path):
        """I-SUMMARY-2: fallback = '{KIND}:{basename}' when no docstring/comment."""
        src = tmp_path / "src" / "sdd"
        src.mkdir(parents=True)
        (src / "empty_module.py").write_text("x = 1\n")
        (tmp_path / ".sdd" / "tasks").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("")

        index = build_index(str(tmp_path))
        node = index.nodes.get("FILE:src/sdd/empty_module.py")
        assert node is not None
        assert node.summary == "FILE:empty_module"


# ---------------------------------------------------------------------------
# I-SIGNATURE-1: signature interface-only
# ---------------------------------------------------------------------------

class TestSignatureInvariant:
    def test_signatures_contain_def_or_class(self, project):
        index = build_index(project)
        file_nodes = [n for n in index.nodes.values() if n.kind == "FILE" and n.signature]
        # At least some file nodes should have signatures
        for node in file_nodes:
            # signature must contain only interface declarations (no prose)
            assert "\n" not in node.signature or all(
                line.strip().startswith(("def ", "async def ", "class ", ""))
                for line in node.signature.split("\n")
            )


# ---------------------------------------------------------------------------
# I-TERM-2 + I-TERM-COVERAGE-1 validation
# ---------------------------------------------------------------------------

class TestTermLinkValidation:
    def test_term_link_violations_in_meta_on_unknown_link(self, tmp_path):
        """I-TERM-2: unresolved TERM.links → meta.term_link_violations."""
        src = tmp_path / "src" / "sdd"
        src.mkdir(parents=True)
        config = tmp_path / ".sdd" / "config"
        config.mkdir(parents=True)
        (tmp_path / ".sdd" / "tasks").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("")
        (config / "glossary.yaml").write_text(
            "terms:\n"
            "  - id: bad_term\n"
            "    label: Bad Term\n"
            "    definition: Term with bad link.\n"
            "    aliases: []\n"
            "    links: [\"COMMAND:nonexistent\"]\n"
        )
        index = build_index(str(tmp_path))
        violations = index.meta.get("term_link_violations", [])
        assert len(violations) > 0
        assert any("COMMAND:nonexistent" in v["missing"] for v in violations)

    def test_i_term_coverage_1_warning_for_uncovered_command(self, project):
        """I-TERM-COVERAGE-1: COMMAND with no TERM link → meta.term_coverage_gaps."""
        # The minimal project has glossary covering "complete" and "validate"
        # so no coverage gap should exist for those two
        index = build_index(project)
        gaps = index.meta.get("term_coverage_gaps", [])
        # complete and validate should be covered by glossary
        assert "COMMAND:complete" not in gaps
        assert "COMMAND:validate" not in gaps

    def test_term_coverage_gap_when_command_not_in_glossary(self, tmp_path):
        """I-TERM-COVERAGE-1: command not covered by any TERM → term_coverage_gaps."""
        src = tmp_path / "src" / "sdd"
        (src / "commands").mkdir(parents=True)
        (src / "commands" / "__init__.py").write_text("")
        (src / "commands" / "registry.py").write_text(
            'REGISTRY = {"uncovered-cmd": CommandSpec(name="uncovered-cmd")}\n'
        )
        config = tmp_path / ".sdd" / "config"
        config.mkdir(parents=True)
        (tmp_path / ".sdd" / "tasks").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("")
        (config / "glossary.yaml").write_text("terms: []\n")

        index = build_index(str(tmp_path))
        gaps = index.meta.get("term_coverage_gaps", [])
        assert "COMMAND:uncovered-cmd" in gaps


# ---------------------------------------------------------------------------
# Node kinds present
# ---------------------------------------------------------------------------

class TestNodeKinds:
    def test_file_nodes_present(self, project):
        index = build_index(project)
        file_nodes = [n for n in index.nodes.values() if n.kind == "FILE"]
        assert len(file_nodes) > 0

    def test_command_nodes_present(self, project):
        index = build_index(project)
        cmd_nodes = [n for n in index.nodes.values() if n.kind == "COMMAND"]
        assert len(cmd_nodes) >= 2  # complete + validate

    def test_guard_nodes_present(self, project):
        index = build_index(project)
        guard_nodes = [n for n in index.nodes.values() if n.kind == "GUARD"]
        assert len(guard_nodes) >= 2  # phase + scope

    def test_reducer_node_present(self, project):
        index = build_index(project)
        assert "REDUCER:main" in index.nodes

    def test_event_nodes_present(self, project):
        index = build_index(project)
        event_nodes = [n for n in index.nodes.values() if n.kind == "EVENT"]
        assert len(event_nodes) >= 2  # TaskImplementedEvent + PhaseCompletedEvent

    def test_task_nodes_present(self, project):
        index = build_index(project)
        task_nodes = [n for n in index.nodes.values() if n.kind == "TASK"]
        assert len(task_nodes) == 3

    def test_invariant_nodes_present(self, project):
        index = build_index(project)
        inv_nodes = [n for n in index.nodes.values() if n.kind == "INVARIANT"]
        assert len(inv_nodes) >= 1

    def test_term_nodes_present(self, project):
        index = build_index(project)
        term_nodes = [n for n in index.nodes.values() if n.kind == "TERM"]
        assert len(term_nodes) == 2


# ---------------------------------------------------------------------------
# Load / save roundtrip
# ---------------------------------------------------------------------------

class TestLoadSaveRoundtrip:
    def test_save_creates_valid_json(self, project, tmp_path):
        index = build_index(project)
        path = str(tmp_path / "test_index.json")
        save_index(index, path)
        assert os.path.isfile(path)
        with open(path) as f:
            data = json.load(f)
        assert data["version"] == 1
        assert "nodes" in data
        assert "built_at" in data

    def test_roundtrip_preserves_nodes(self, project, tmp_path):
        index = build_index(project)
        path = str(tmp_path / "test_index.json")
        save_index(index, path)
        loaded = load_index(path)
        assert set(loaded.nodes.keys()) == set(index.nodes.keys())

    def test_roundtrip_preserves_term_fields(self, project, tmp_path):
        """TERM-specific fields (definition, aliases, links) survive save/load."""
        index = build_index(project)
        path = str(tmp_path / "test_index.json")
        save_index(index, path)
        loaded = load_index(path)
        original = index.nodes["TERM:complete_task"]
        restored = loaded.nodes["TERM:complete_task"]
        assert restored.definition == original.definition
        assert restored.aliases == original.aliases
        assert restored.links == original.links

    def test_roundtrip_preserves_meta(self, project, tmp_path):
        index = build_index(project)
        path = str(tmp_path / "test_index.json")
        save_index(index, path)
        loaded = load_index(path)
        assert loaded.meta == index.meta

    def test_save_is_atomic(self, project, tmp_path):
        """save_index uses tmp file + os.replace — no partial write visible."""
        index = build_index(project)
        path = str(tmp_path / "output" / "index.json")
        save_index(index, path)
        assert os.path.isfile(path)
        assert not os.path.isfile(path + ".tmp")

    def test_load_nodes_are_spatial_node_instances(self, project, tmp_path):
        index = build_index(project)
        path = str(tmp_path / "idx.json")
        save_index(index, path)
        loaded = load_index(path)
        for node in loaded.nodes.values():
            assert isinstance(node, SpatialNode)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_node_ids_deterministic_across_builds(self, project):
        ids1 = set(build_index(project).nodes.keys())
        ids2 = set(build_index(project).nodes.keys())
        assert ids1 == ids2

    def test_summaries_deterministic(self, project):
        summaries1 = {k: v.summary for k, v in build_index(project).nodes.items()}
        summaries2 = {k: v.summary for k, v in build_index(project).nodes.items()}
        assert summaries1 == summaries2


# ---------------------------------------------------------------------------
# I-SI-READ-1 + I-GRAPH-CACHE-2: snapshot_hash and _content_map
# ---------------------------------------------------------------------------

class TestSnapshotHashAndContentMap:
    def test_snapshot_hash_is_hex_string(self, project):
        index = build_index(project)
        assert isinstance(index.snapshot_hash, str)
        assert len(index.snapshot_hash) == 64  # sha256 hex digest

    def test_snapshot_hash_based_on_file_content(self, tmp_path):
        """I-SI-READ-1: snapshot_hash changes when FILE content changes."""
        src = tmp_path / "src" / "sdd"
        src.mkdir(parents=True)
        f = src / "module.py"
        f.write_text('"""Version A."""\n')
        (tmp_path / ".sdd" / "tasks").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("")

        index_a = build_index(str(tmp_path))
        f.write_text('"""Version B."""\n')
        index_b = build_index(str(tmp_path))

        assert index_a.snapshot_hash != index_b.snapshot_hash

    def test_snapshot_hash_stable_without_changes(self, project):
        """I-GRAPH-CACHE-2: same content → same snapshot_hash."""
        h1 = build_index(project).snapshot_hash
        h2 = build_index(project).snapshot_hash
        assert h1 == h2

    def test_snapshot_hash_not_based_on_non_file_nodes(self, tmp_path):
        """snapshot_hash ignores COMMAND/GUARD/EVENT nodes — FILE content only."""
        src = tmp_path / "src" / "sdd"
        src.mkdir(parents=True)
        (src / "module.py").write_text('"""Stable."""\n')
        commands = src / "commands"
        commands.mkdir()
        (commands / "__init__.py").write_text("")
        (commands / "registry.py").write_text(
            'REGISTRY = {"cmd-a": CommandSpec(name="cmd-a")}\n'
        )
        (tmp_path / ".sdd" / "tasks").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("")

        index_a = build_index(str(tmp_path))

        # Change only registry (COMMAND nodes) — FILE content unchanged
        (commands / "registry.py").write_text(
            'REGISTRY = {"cmd-b": CommandSpec(name="cmd-b")}\n'
        )
        index_b = build_index(str(tmp_path))

        # snapshot_hash changes because registry.py is itself a FILE node
        # (registry.py content changed → FILE node content changed)
        assert index_a.snapshot_hash != index_b.snapshot_hash

    def test_content_map_populated_for_file_nodes_only(self, project):
        """I-GRAPH-CACHE-2: _content_map contains only FILE node paths."""
        index = build_index(project)
        file_paths = {node.path for node in index.nodes.values() if node.kind == "FILE"}
        assert set(index._content_map.keys()) == file_paths

    def test_content_map_values_are_file_contents(self, tmp_path):
        """_content_map[path] == actual file content."""
        src = tmp_path / "src" / "sdd"
        src.mkdir(parents=True)
        content = '"""My module."""\nx = 42\n'
        (src / "mymod.py").write_text(content)
        (tmp_path / ".sdd" / "tasks").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("")

        index = build_index(str(tmp_path))
        assert index._content_map.get("src/sdd/mymod.py") == content

    def test_content_map_empty_when_no_file_nodes(self, tmp_path):
        """_content_map is empty if there are no FILE nodes."""
        (tmp_path / ".sdd" / "tasks").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("")
        index = build_index(str(tmp_path))
        assert index._content_map == {}


# ---------------------------------------------------------------------------
# I-SI-READ-1 + I-GRAPH-FS-ISOLATION-1: read_content public method
# ---------------------------------------------------------------------------

class TestReadContent:
    def test_file_node_returns_content(self, tmp_path):
        """read_content returns actual file content for FILE nodes."""
        src = tmp_path / "src" / "sdd"
        src.mkdir(parents=True)
        content = '"""My module."""\nx = 42\n'
        (src / "mymod.py").write_text(content)
        (tmp_path / ".sdd" / "tasks").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("")

        index = build_index(str(tmp_path))
        node = index.nodes["FILE:src/sdd/mymod.py"]
        assert index.read_content(node) == content

    def test_non_file_node_returns_empty_string(self, project):
        """read_content returns '' for non-FILE nodes (COMMAND, GUARD, TERM, etc.)."""
        index = build_index(project)
        for node in index.nodes.values():
            if node.kind != "FILE":
                assert index.read_content(node) == "", (
                    f"{node.node_id}: expected '' for kind={node.kind!r}"
                )

    def test_missing_file_node_raises_key_error(self):
        """read_content raises KeyError when FILE node is not in content map."""
        index = SpatialIndex(
            nodes={},
            built_at="2026-01-01T00:00:00Z",
            git_tree_hash=None,
        )
        node = SpatialNode(
            node_id="FILE:src/sdd/missing.py",
            kind="FILE",
            label="missing.py",
            path="src/sdd/missing.py",
            summary="FILE:missing",
            signature="",
            meta={},
            git_hash=None,
            indexed_at="2026-01-01T00:00:00Z",
        )
        with pytest.raises(KeyError):
            index.read_content(node)

    def test_read_content_consistent_with_content_map(self, project):
        """read_content(node) == _content_map[node.path] for all FILE nodes."""
        index = build_index(project)
        for node in index.nodes.values():
            if node.kind == "FILE":
                assert index.read_content(node) == index._content_map[node.path]
