import pytest
from dataclasses import FrozenInstanceError

from sdd.spatial.nodes import SpatialEdge, SpatialNode


def _node(**kwargs) -> SpatialNode:
    defaults = dict(
        node_id="COMMAND:complete",
        kind="COMMAND",
        label="Complete Task",
        path="src/sdd/commands/complete.py",
        summary="Mark task T-NNN as done",
        signature="def complete(task_id: str) -> None: ...",
        meta={},
        git_hash="abc123def456",
        indexed_at="2026-04-24T00:00:00Z",
    )
    return SpatialNode(**{**defaults, **kwargs})


class TestSpatialNodeConstruction:
    def test_basic_construction(self):
        node = _node()
        assert node.node_id == "COMMAND:complete"
        assert node.kind == "COMMAND"
        assert node.label == "Complete Task"
        assert node.path == "src/sdd/commands/complete.py"

    def test_frozen(self):
        node = _node()
        with pytest.raises(FrozenInstanceError):
            node.node_id = "changed"  # type: ignore[misc]

    def test_term_defaults(self):
        node = _node(node_id="TERM:activate_phase", kind="TERM", path=None, git_hash=None)
        assert node.definition == ""
        assert node.aliases == ()
        assert node.links == ()

    def test_term_with_fields(self):
        node = _node(
            node_id="TERM:activate_phase",
            kind="TERM",
            path=None,
            git_hash=None,
            definition="Human-only phase gate",
            aliases=("phase activation", "sdd activate-phase"),
            links=("COMMAND:activate-phase", "EVENT:PhaseActivated"),
        )
        assert node.definition == "Human-only phase gate"
        assert "phase activation" in node.aliases
        assert "COMMAND:activate-phase" in node.links

    def test_non_term_has_empty_links(self):
        node = _node()
        assert node.links == ()
        assert node.aliases == ()
        assert node.definition == ""


class TestSummaryInvariants:
    def test_i_summary_1_single_line_enforced(self):
        """I-SUMMARY-1: summary must be exactly 1 line."""
        with pytest.raises(ValueError, match="I-SUMMARY-1"):
            _node(summary="line1\nline2")

    def test_i_summary_2_empty_rejected(self):
        """I-SUMMARY-2: summary must never be empty."""
        with pytest.raises(ValueError, match="I-SUMMARY-2"):
            _node(summary="")

    def test_i_summary_2_fallback_format(self):
        """I-SUMMARY-2: fallback format '{KIND}:{basename}' satisfies both invariants."""
        node = _node(summary="COMMAND:complete")
        assert node.summary == "COMMAND:complete"
        assert "\n" not in node.summary


class TestSignatureInvariant:
    def test_i_signature_1_interface_only(self):
        """I-SIGNATURE-1: signature contains only interface declarations (no prose)."""
        node = _node(signature="def complete(task_id: str) -> None: ...")
        assert node.signature
        # signature field is free-form string; IndexBuilder enforces interface-only content
        assert "def complete" in node.signature

    def test_signature_can_include_class_definition(self):
        node = _node(signature="class SpatialNode:\n    node_id: str\n    kind: str")
        assert "class SpatialNode" in node.signature


class TestDddInvariant:
    def test_i_ddd_1_term_links_primary_source(self):
        """I-DDD-1: SpatialNode.links for TERM is the primary source of means edges."""
        node = _node(
            node_id="TERM:complete_task",
            kind="TERM",
            path=None,
            git_hash=None,
            links=("COMMAND:complete", "EVENT:TaskImplementedEvent"),
        )
        assert "COMMAND:complete" in node.links
        assert "EVENT:TaskImplementedEvent" in node.links

    def test_i_ddd_1_links_tuple_immutable(self):
        """I-DDD-1: links tuple is immutable (frozen dataclass)."""
        node = _node(
            node_id="TERM:complete_task",
            kind="TERM",
            path=None,
            git_hash=None,
            links=("COMMAND:complete",),
        )
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            node.links = ("other",)  # type: ignore[misc]


class TestSpatialEdge:
    def test_construction(self):
        edge = SpatialEdge(
            edge_id="abc123def456",
            src="TERM:complete_task",
            dst="COMMAND:complete",
            kind="means",
            meta={},
        )
        assert edge.edge_id == "abc123def456"
        assert edge.src == "TERM:complete_task"
        assert edge.dst == "COMMAND:complete"
        assert edge.kind == "means"

    def test_frozen(self):
        edge = SpatialEdge(
            edge_id="abc123def456",
            src="TERM:complete_task",
            dst="COMMAND:complete",
            kind="means",
            meta={},
        )
        with pytest.raises(FrozenInstanceError):
            edge.src = "changed"  # type: ignore[misc]

    def test_all_edge_kinds(self):
        for kind in ("imports", "emits", "defined_in", "depends_on", "tested_by", "verified_by", "means"):
            edge = SpatialEdge(edge_id="x", src="A", dst="B", kind=kind, meta={})
            assert edge.kind == kind
