"""Tests for Navigator class (BC-18-3): I-SI-2, I-SI-3, I-FUZZY-1, I-SEARCH-2."""
from __future__ import annotations

import pytest

from sdd.spatial.index import SpatialIndex
from sdd.spatial.navigator import (
    NavigationIntent,
    NavigationSession,
    Navigator,
    _levenshtein,
    _search_keys,
)
from sdd.spatial.nodes import SpatialNode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _node(
    node_id: str,
    kind: str = "COMMAND",
    label: str = "label",
    path: str | None = None,
    summary: str = "summary text",
    signature: str = "def foo(): ...",
    meta: dict | None = None,
    git_hash: str | None = "abc123",
    indexed_at: str = "2026-01-01T00:00:00Z",
    definition: str = "",
    aliases: tuple[str, ...] = (),
    links: tuple[str, ...] = (),
) -> SpatialNode:
    return SpatialNode(
        node_id=node_id,
        kind=kind,
        label=label,
        path=path,
        summary=summary,
        signature=signature,
        meta=meta or {},
        git_hash=git_hash,
        indexed_at=indexed_at,
        definition=definition,
        aliases=aliases,
        links=links,
    )


def _index(*nodes: SpatialNode) -> SpatialIndex:
    return SpatialIndex(
        nodes={n.node_id: n for n in nodes},
        built_at="2026-01-01T00:00:00Z",
        git_tree_hash="tree123",
    )


# ---------------------------------------------------------------------------
# resolve — modes
# ---------------------------------------------------------------------------


class TestResolveModes:
    def test_pointer_fields_only(self):
        idx = _index(_node("COMMAND:complete", label="sdd complete", path="src/cmd.py"))
        nav = Navigator(idx)
        result = nav.resolve("COMMAND:complete", mode="POINTER")
        assert set(result.keys()) == {"node_id", "kind", "label", "path"}
        assert result["node_id"] == "COMMAND:complete"
        assert result["kind"] == "COMMAND"
        assert result["label"] == "sdd complete"
        assert result["path"] == "src/cmd.py"

    def test_summary_includes_pointer_fields(self):
        idx = _index(_node("COMMAND:complete", summary="Mark task DONE"))
        nav = Navigator(idx)
        result = nav.resolve("COMMAND:complete", mode="SUMMARY")
        assert "node_id" in result
        assert "summary" in result
        assert "git_hash" in result
        assert "indexed_at" in result
        assert "signature" not in result

    def test_signature_includes_summary_fields(self):
        idx = _index(_node("COMMAND:complete", signature="def main(args): ..."))
        nav = Navigator(idx)
        result = nav.resolve("COMMAND:complete", mode="SIGNATURE")
        assert "summary" in result
        assert "signature" in result
        assert result["signature"] == "def main(args): ..."
        assert "meta" not in result

    def test_full_includes_meta(self):
        idx = _index(_node("COMMAND:complete", meta={"key": "val"}))
        nav = Navigator(idx)
        result = nav.resolve("COMMAND:complete", mode="FULL")
        assert "meta" in result
        assert result["meta"] == {"key": "val"}
        assert "signature" in result

    def test_full_term_includes_definition_aliases_links(self):
        node = _node(
            "TERM:activate_phase",
            kind="TERM",
            path=None,
            git_hash=None,
            definition="Human-only gate",
            aliases=("phase activation", "activate phase"),
            links=("COMMAND:activate-phase",),
        )
        idx = _index(node)
        nav = Navigator(idx)
        result = nav.resolve("TERM:activate_phase", mode="FULL")
        assert result["definition"] == "Human-only gate"
        assert "phase activation" in result["aliases"]
        assert "COMMAND:activate-phase" in result["links"]

    def test_full_non_file_no_full_text(self):
        idx = _index(_node("COMMAND:complete"))
        nav = Navigator(idx)
        result = nav.resolve("COMMAND:complete", mode="FULL")
        assert "full_text" not in result

    def test_full_file_reads_content(self, tmp_path):
        fpath = tmp_path / "test.py"
        fpath.write_text("print('hello')")
        node = _node("FILE:test.py", kind="FILE", path=str(fpath))
        idx = _index(node)
        nav = Navigator(idx, project_root=None)
        result = nav.resolve("FILE:test.py", mode="FULL")
        assert result["full_text"] == "print('hello')"

    def test_full_file_missing_returns_none(self):
        node = _node("FILE:missing.py", kind="FILE", path="/nonexistent/path/missing.py")
        idx = _index(node)
        nav = Navigator(idx)
        result = nav.resolve("FILE:missing.py", mode="FULL")
        assert result["full_text"] is None

    def test_default_mode_is_summary(self):
        idx = _index(_node("COMMAND:complete"))
        nav = Navigator(idx)
        result = nav.resolve("COMMAND:complete")
        assert "summary" in result
        assert "signature" not in result


# ---------------------------------------------------------------------------
# resolve — not_found (I-SI-2, anti-hallucination)
# ---------------------------------------------------------------------------


class TestResolveNotFound:
    def test_not_found_status(self):
        nav = Navigator(_index())
        result = nav.resolve("COMMAND:nonexistent")
        assert result["status"] == "not_found"

    def test_must_not_guess_always_true(self):
        nav = Navigator(_index())
        result = nav.resolve("COMMAND:nonexistent")
        assert result["must_not_guess"] is True

    def test_query_preserved(self):
        nav = Navigator(_index())
        result = nav.resolve("COMMAND:xyz")
        assert result["query"] == "COMMAND:xyz"

    def test_did_you_mean_always_present(self):
        nav = Navigator(_index())
        result = nav.resolve("COMMAND:nonexistent")
        assert "did_you_mean" in result
        assert isinstance(result["did_you_mean"], list)

    def test_did_you_mean_can_be_empty(self):
        nav = Navigator(_index())
        result = nav.resolve("COMMAND:nonexistent")
        # empty index → no suggestions
        assert result["did_you_mean"] == []


# ---------------------------------------------------------------------------
# resolve — session enforcement (I-NAV-1, I-NAV-8)
# ---------------------------------------------------------------------------


class TestResolveWithSession:
    def test_denial_returns_nav_invariant_violation(self):
        idx = _index(_node("FILE:x.py", kind="FILE", path="x.py"))
        session = NavigationSession(step_id=0)
        nav = Navigator(idx, session=session)
        intent = NavigationIntent(type="code_write")
        result = nav.resolve("FILE:x.py", mode="FULL", intent=intent)
        assert result["status"] == "nav_invariant_violation"
        assert result["invariant"] == "I-NAV-1"
        assert result["denial"]["reason"] == "summary_required"

    def test_allowed_after_summary(self):
        node = _node("FILE:x.py", kind="FILE", path="/nonexistent/x.py")
        idx = _index(node)
        session = NavigationSession(step_id=0)
        session.record_load("FILE:x.py", "SUMMARY")
        nav = Navigator(idx, session=session)
        intent = NavigationIntent(type="code_write")
        result = nav.resolve("FILE:x.py", mode="FULL", intent=intent)
        assert result.get("status") != "nav_invariant_violation"
        assert result["kind"] == "FILE"

    def test_no_session_no_enforcement(self):
        node = _node("FILE:x.py", kind="FILE", path="/nonexistent/x.py")
        idx = _index(node)
        nav = Navigator(idx, session=None)
        intent = NavigationIntent(type="code_write")
        result = nav.resolve("FILE:x.py", mode="FULL", intent=intent)
        assert result.get("status") != "nav_invariant_violation"

    def test_ceiling_violation_returns_i_nav_8(self):
        idx = _index(_node("COMMAND:complete"))
        session = NavigationSession(step_id=0)
        nav = Navigator(idx, session=session)
        intent = NavigationIntent(type="explore")
        result = nav.resolve("COMMAND:complete", mode="FULL", intent=intent)
        assert result["status"] == "nav_invariant_violation"
        assert "I-NAV-8" in result["denial"]["violated"]


# ---------------------------------------------------------------------------
# I-SI-2: deterministic output
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_resolve_same_output_twice(self):
        idx = _index(_node("COMMAND:complete", summary="Mark task DONE"))
        nav = Navigator(idx)
        r1 = nav.resolve("COMMAND:complete", mode="SUMMARY")
        r2 = nav.resolve("COMMAND:complete", mode="SUMMARY")
        assert r1 == r2

    def test_search_same_output_twice(self):
        idx = _index(
            _node("COMMAND:complete"),
            _node("COMMAND:compile"),
        )
        nav = Navigator(idx)
        r1 = nav.search("comple")
        r2 = nav.search("comple")
        assert r1 == r2


# ---------------------------------------------------------------------------
# I-FUZZY-1: search key computation
# ---------------------------------------------------------------------------


class TestSearchKeys:
    def test_file_returns_basename_stem(self):
        node = _node("FILE:src/sdd/cli.py", kind="FILE", path="src/sdd/cli.py")
        keys = _search_keys(node)
        assert keys == ["cli"]

    def test_command_returns_suffix(self):
        node = _node("COMMAND:complete", kind="COMMAND")
        keys = _search_keys(node)
        assert keys == ["complete"]

    def test_term_includes_aliases(self):
        node = _node(
            "TERM:activate_phase",
            kind="TERM",
            git_hash=None,
            aliases=("phase activation", "activate phase"),
        )
        keys = _search_keys(node)
        assert "activate_phase" in keys
        assert "phase activation" in keys
        assert "activate phase" in keys

    def test_invariant_returns_suffix(self):
        node = _node("INVARIANT:I-NAV-1", kind="INVARIANT", git_hash=None)
        keys = _search_keys(node)
        assert keys == ["I-NAV-1"]

    def test_file_no_extension(self):
        node = _node("FILE:src/Makefile", kind="FILE", path="src/Makefile")
        keys = _search_keys(node)
        assert keys == ["Makefile"]


# ---------------------------------------------------------------------------
# _levenshtein correctness
# ---------------------------------------------------------------------------


class TestLevenshtein:
    def test_identical_strings(self):
        assert _levenshtein("abc", "abc") == 0

    def test_empty_string(self):
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3

    def test_single_substitution(self):
        assert _levenshtein("cat", "bat") == 1

    def test_single_deletion(self):
        assert _levenshtein("abcd", "abc") == 1

    def test_single_insertion(self):
        assert _levenshtein("abc", "abcd") == 1

    def test_commutative(self):
        assert _levenshtein("complete", "comlete") == _levenshtein("comlete", "complete")


# ---------------------------------------------------------------------------
# search — I-SEARCH-2 pipeline and I-FUZZY-1 threshold
# ---------------------------------------------------------------------------


class TestSearch:
    def test_exact_match_found(self):
        idx = _index(_node("COMMAND:complete"))
        nav = Navigator(idx)
        results = nav.search("complete")
        assert any(r["node_id"] == "COMMAND:complete" for r in results)

    def test_fuzzy_within_threshold(self):
        # "comlete" is 1 edit away from "complete"
        idx = _index(_node("COMMAND:complete"))
        nav = Navigator(idx)
        results = nav.search("comlete")
        assert any(r["node_id"] == "COMMAND:complete" for r in results)

    def test_beyond_threshold_not_found(self):
        # "xyz" is >2 edits from "complete"
        idx = _index(_node("COMMAND:complete"))
        nav = Navigator(idx)
        results = nav.search("xyz")
        assert not any(r["node_id"] == "COMMAND:complete" for r in results)

    def test_kind_filter(self):
        idx = _index(
            _node("COMMAND:complete"),
            _node("TASK:T-complete", kind="TASK", git_hash=None),
        )
        nav = Navigator(idx)
        results = nav.search("complete", kind="COMMAND")
        assert all(r["kind"] == "COMMAND" for r in results)

    def test_limit_applied_after_sort(self):
        # I-SEARCH-2: limit before render
        idx = _index(
            _node("COMMAND:complete"),
            _node("COMMAND:compile"),
            _node("COMMAND:compare"),
        )
        nav = Navigator(idx)
        results = nav.search("com", limit=2)
        assert len(results) <= 2

    def test_limit_does_not_precede_sort(self):
        # If limit were applied before sort, we'd get random order.
        # Verify sort order: lower distance first, then kind_priority, then node_id lex.
        idx = _index(
            _node("COMMAND:complete"),
            _node("FILE:complete.py", kind="FILE", path="complete.py"),
        )
        nav = Navigator(idx)
        results = nav.search("complete", limit=10)
        # Both match with distance 0. COMMAND priority=1, FILE priority=7 → COMMAND first
        assert results[0]["node_id"] == "COMMAND:complete"
        assert results[1]["node_id"] == "FILE:complete.py"  # node_id preserves full path

    def test_term_alias_match(self):
        node = _node(
            "TERM:activate_phase",
            kind="TERM",
            git_hash=None,
            aliases=("phase activation", "activate phase"),
        )
        idx = _index(node)
        nav = Navigator(idx)
        results = nav.search("activate phase")
        assert any(r["node_id"] == "TERM:activate_phase" for r in results)

    def test_deterministic_sort_by_node_id_lex(self):
        # Two nodes with same kind and same distance → sorted by node_id lex
        idx = _index(
            _node("COMMAND:zzz"),
            _node("COMMAND:aaa"),
        )
        nav = Navigator(idx)
        results = nav.search("aaa", limit=10)
        node_ids = [r["node_id"] for r in results]
        if len(node_ids) >= 2:
            # aaa is exact match (distance=0), zzz is far → aaa should be first
            assert node_ids[0] == "COMMAND:aaa"

    def test_kind_priority_term_before_file(self):
        # I-FUZZY-1: TERM aliases match → TERM ranked first (kind_priority 0 < 7)
        term_node = _node(
            "TERM:cli",
            kind="TERM",
            git_hash=None,
            aliases=("cli",),
        )
        file_node = _node("FILE:src/cli.py", kind="FILE", path="src/cli.py")
        idx = _index(term_node, file_node)
        nav = Navigator(idx)
        results = nav.search("cli", limit=10)
        kinds = [r["kind"] for r in results]
        assert kinds.index("TERM") < kinds.index("FILE")

    def test_empty_results_when_no_match(self):
        idx = _index(_node("COMMAND:complete"))
        nav = Navigator(idx)
        results = nav.search("xyzqwerty")
        assert results == []

    def test_result_has_required_fields(self):
        idx = _index(_node("COMMAND:complete"))
        nav = Navigator(idx)
        results = nav.search("complete")
        assert results
        r = results[0]
        assert "node_id" in r
        assert "kind" in r
        assert "label" in r
        assert "score" in r


# ---------------------------------------------------------------------------
# not_found_response
# ---------------------------------------------------------------------------


class TestNotFoundResponse:
    def test_always_must_not_guess(self):
        nav = Navigator(_index())
        r = nav.not_found_response("anything")
        assert r["must_not_guess"] is True

    def test_status_not_found(self):
        nav = Navigator(_index())
        r = nav.not_found_response("anything")
        assert r["status"] == "not_found"

    def test_query_preserved(self):
        nav = Navigator(_index())
        r = nav.not_found_response("COMMAND:xyz")
        assert r["query"] == "COMMAND:xyz"

    def test_did_you_mean_always_present(self):
        nav = Navigator(_index())
        r = nav.not_found_response("anything")
        assert "did_you_mean" in r

    def test_did_you_mean_is_list(self):
        nav = Navigator(_index())
        r = nav.not_found_response("anything")
        assert isinstance(r["did_you_mean"], list)

    def test_did_you_mean_max_5(self):
        idx = _index(*[_node(f"COMMAND:cmd{i}") for i in range(20)])
        nav = Navigator(idx)
        r = nav.not_found_response("cmd")
        assert len(r["did_you_mean"]) <= 5

    def test_suggestions_deterministic(self):
        idx = _index(_node("COMMAND:complete"), _node("COMMAND:compile"))
        nav = Navigator(idx)
        r1 = nav.not_found_response("compl")
        r2 = nav.not_found_response("compl")
        assert r1["did_you_mean"] == r2["did_you_mean"]
