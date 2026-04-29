"""Integration-level tests for ContextRuntime (T-5118).

Covers:
  - DoD 3: ContextRuntime instantiable with mocks
  - I-RUNTIME-BOUNDARY-1: ContextRuntime must not import GraphService
  - I-ENGINE-INPUTS-1: DocProvider created from SpatialIndex; raw SpatialIndex never passed to engine
  - rag_client propagated from construction through to engine.query()
"""
from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

import pytest

from sdd.context_kernel.documents import DocProvider
from sdd.context_kernel.engine import ContextEngine
from sdd.context_kernel.rag_types import NavigationResponse
from sdd.context_kernel.runtime import ContextRuntime
from sdd.graph.types import DeterministicGraph, Node
from sdd.policy import Budget, NavigationPolicy, RagMode
from sdd.spatial.index import SpatialIndex

_PROJECT_ROOT = pathlib.Path(__file__).parents[3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(node_id: str) -> Node:
    return Node(node_id=node_id, kind="FILE", label=node_id, summary="", meta={})


def _graph(*node_ids: str) -> DeterministicGraph:
    nodes = {nid: _node(nid) for nid in node_ids}
    return DeterministicGraph(nodes=nodes, edges_out={}, edges_in={}, source_snapshot_hash="rt_hash")


def _policy() -> NavigationPolicy:
    return NavigationPolicy(Budget(max_nodes=5, max_edges=10, max_chars=4096), RagMode.OFF)


def _mock_engine() -> MagicMock:
    engine = MagicMock(spec=ContextEngine)
    engine.query.return_value = MagicMock(spec=NavigationResponse)
    return engine


def _mock_index() -> MagicMock:
    index = MagicMock(spec=SpatialIndex)
    index.nodes = {}  # DocProvider calls index.nodes.keys() during __init__
    return index


# ---------------------------------------------------------------------------
# DoD 3: Instantiation
# ---------------------------------------------------------------------------

class TestRuntimeInstantiation:
    def test_instantiable_with_mock_engine(self) -> None:
        """DoD 3: ContextRuntime instantiable with injected ContextEngine mock."""
        runtime = ContextRuntime(engine=_mock_engine())
        assert runtime is not None

    def test_rag_client_defaults_to_none(self) -> None:
        runtime = ContextRuntime(engine=_mock_engine())
        assert runtime._rag_client is None

    def test_rag_client_stored_when_provided(self) -> None:
        rag_client = MagicMock()
        runtime = ContextRuntime(engine=_mock_engine(), rag_client=rag_client)
        assert runtime._rag_client is rag_client


# ---------------------------------------------------------------------------
# I-RUNTIME-BOUNDARY-1: no GraphService import
# ---------------------------------------------------------------------------

def _imported_names(rel_path: str) -> set[str]:
    """Return all names referenced in import statements of the given source file."""
    import ast
    src = (_PROJECT_ROOT / rel_path).read_text()
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            for alias in node.names:
                names.add(alias.name)
    return names


class TestRuntimeBoundary:
    def test_does_not_import_graph_service(self) -> None:
        """I-RUNTIME-BOUNDARY-1: runtime.py must not import GraphService."""
        assert "GraphService" not in _imported_names("src/sdd/context_kernel/runtime.py"), \
            "I-RUNTIME-BOUNDARY-1 violated: GraphService imported in runtime.py"


# ---------------------------------------------------------------------------
# I-ENGINE-INPUTS-1: DocProvider injection
# ---------------------------------------------------------------------------

class TestDocProviderInjection:
    def test_factory_called_with_index(self) -> None:
        """runtime.query() invokes doc_provider_factory(index)."""
        engine = _mock_engine()
        doc_provider = MagicMock(spec=DocProvider)
        factory = MagicMock(return_value=doc_provider)
        runtime = ContextRuntime(engine=engine, doc_provider_factory=factory)

        index = _mock_index()
        runtime.query(_graph("FILE:z"), _policy(), index, "FILE:z")

        factory.assert_called_once_with(index)

    def test_engine_receives_doc_provider_not_spatial_index(self) -> None:
        """ContextEngine.query() receives DocProvider; SpatialIndex never passed to engine."""
        engine = _mock_engine()
        doc_provider = MagicMock(spec=DocProvider)
        factory = MagicMock(return_value=doc_provider)
        runtime = ContextRuntime(engine=engine, doc_provider_factory=factory)

        index = _mock_index()
        runtime.query(_graph("FILE:w"), _policy(), index, "FILE:w")

        engine.query.assert_called_once()
        all_args = list(engine.query.call_args.args) + list(engine.query.call_args.kwargs.values())
        assert doc_provider in all_args, "DocProvider must be forwarded to ContextEngine"
        assert index not in all_args, "SpatialIndex must NOT be passed to ContextEngine"


# ---------------------------------------------------------------------------
# Full pipeline: runtime.query() → engine.query()
# ---------------------------------------------------------------------------

class TestRuntimeQueryPipeline:
    def test_query_delegates_to_engine_once(self) -> None:
        """runtime.query() calls engine.query() exactly once."""
        engine = _mock_engine()
        runtime = ContextRuntime(engine=engine)

        response = runtime.query(_graph("FILE:q"), _policy(), _mock_index(), "FILE:q")

        engine.query.assert_called_once()
        assert response is engine.query.return_value

    def test_graph_and_policy_forwarded_unchanged(self) -> None:
        """graph and policy objects are forwarded to engine.query() unchanged."""
        engine = _mock_engine()
        runtime = ContextRuntime(engine=engine)

        graph = _graph("FILE:v")
        policy = _policy()
        runtime.query(graph, policy, _mock_index(), "FILE:v")

        all_args = list(engine.query.call_args.args) + list(engine.query.call_args.kwargs.values())
        assert graph in all_args
        assert policy in all_args

    def test_node_id_forwarded_to_engine(self) -> None:
        engine = _mock_engine()
        runtime = ContextRuntime(engine=engine)

        runtime.query(_graph("FILE:n"), _policy(), _mock_index(), "FILE:n")

        all_args = list(engine.query.call_args.args) + list(engine.query.call_args.kwargs.values())
        assert "FILE:n" in all_args

    def test_rag_client_propagated_to_engine(self) -> None:
        """rag_client injected at construction is passed through as kwarg to engine.query()."""
        engine = _mock_engine()
        rag_client = MagicMock()
        runtime = ContextRuntime(engine=engine, rag_client=rag_client)

        runtime.query(_graph("FILE:p"), _policy(), _mock_index(), "FILE:p")

        kwargs = engine.query.call_args.kwargs
        assert kwargs.get("rag_client") is rag_client

    def test_none_rag_client_propagated(self) -> None:
        """rag_client=None is passed through explicitly."""
        engine = _mock_engine()
        runtime = ContextRuntime(engine=engine, rag_client=None)

        runtime.query(_graph("FILE:o"), _policy(), _mock_index(), "FILE:o")

        kwargs = engine.query.call_args.kwargs
        assert kwargs.get("rag_client") is None
