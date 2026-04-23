"""Tests for build_dag + topological_order — Spec_v3 §4.10, I-SCH-1..6."""
from __future__ import annotations

import pytest

from sdd.core.errors import CyclicDependency, MissingContext, ParallelGroupConflict
from sdd.domain.tasks import TaskNode, build_dag, topological_order
from sdd.domain.tasks.parser import Task


def _task(task_id: str, depends_on: tuple[str, ...] = (), parallel_group: str | None = None) -> Task:
    return Task(
        task_id=task_id,
        title=task_id,
        status="TODO",
        spec_section="",
        inputs=(),
        outputs=(),
        checks=(),
        spec_refs=(),
        produces_invariants=(),
        requires_invariants=(),
        depends_on=depends_on,
        parallel_group=parallel_group,
    )


# ─── build_dag ────────────────────────────────────────────────────────────────

def test_build_dag_empty_returns_empty() -> None:
    """I-SCH-3: build_dag([]) → {}."""
    assert build_dag([]) == {}


def test_build_dag_raises_cyclic_dependency() -> None:
    """I-SCH-4: build_dag raises CyclicDependency on cycle."""
    tasks = [
        _task("T-A", depends_on=("T-B",)),
        _task("T-B", depends_on=("T-A",)),
    ]
    with pytest.raises(CyclicDependency):
        build_dag(tasks)


def test_build_dag_raises_missing_context_unknown_dep() -> None:
    """I-SCH-4: build_dag raises MissingContext when depends_on references unknown task_id."""
    tasks = [_task("T-A", depends_on=("T-UNKNOWN",))]
    with pytest.raises(MissingContext):
        build_dag(tasks)


# ─── topological_order ────────────────────────────────────────────────────────

def test_topological_order_empty_dag() -> None:
    """I-SCH-3: topological_order({}) → []."""
    assert topological_order({}) == []


def test_topological_order_simple_chain() -> None:
    """I-SCH-1: T-A → T-B → T-C produces 3 sequential layers."""
    tasks = [
        _task("T-A"),
        _task("T-B", depends_on=("T-A",)),
        _task("T-C", depends_on=("T-B",)),
    ]
    dag = build_dag(tasks)
    layers = topological_order(dag)
    assert len(layers) == 3
    assert "T-A" in layers[0]
    assert "T-B" in layers[1]
    assert "T-C" in layers[2]


def test_topological_order_parallel_group_colocated() -> None:
    """I-SCH-5: tasks with same parallel_group end up in the same layer."""
    tasks = [
        _task("T-A"),
        _task("T-B", depends_on=("T-A",), parallel_group="g1"),
        _task("T-C", depends_on=("T-A",), parallel_group="g1"),
    ]
    dag = build_dag(tasks)
    layers = topological_order(dag)
    # T-B and T-C must be co-located
    found_b = found_c = -1
    for i, layer in enumerate(layers):
        if "T-B" in layer:
            found_b = i
        if "T-C" in layer:
            found_c = i
    assert found_b == found_c, f"T-B in layer {found_b}, T-C in layer {found_c}"


def test_topological_order_no_duplicates() -> None:
    """I-SCH-2: every task_id appears exactly once across all layers."""
    tasks = [
        _task("T-A"),
        _task("T-B", depends_on=("T-A",)),
        _task("T-C", depends_on=("T-A",)),
        _task("T-D", depends_on=("T-B", "T-C")),
    ]
    dag = build_dag(tasks)
    layers = topological_order(dag)
    all_ids = [tid for layer in layers for tid in layer]
    assert sorted(all_ids) == sorted(dag.keys())
    assert len(all_ids) == len(set(all_ids))


def test_topological_order_raises_on_cycle() -> None:
    """I-SCH-1: topological_order raises CyclicDependency when cycle exists in dag."""
    # Manually inject a cyclic dag (bypassing build_dag's detection)
    dag = {
        "T-A": TaskNode(task_id="T-A", depends_on=("T-B",), parallel_group=None),
        "T-B": TaskNode(task_id="T-B", depends_on=("T-A",), parallel_group=None),
    }
    with pytest.raises(CyclicDependency):
        topological_order(dag)


def test_topological_order_raises_parallel_group_conflict() -> None:
    """I-SCH-5/6: raises ParallelGroupConflict when parallel_group members cannot be co-located."""
    tasks = [
        _task("T-A", parallel_group="g1"),
        _task("T-B", depends_on=("T-A",), parallel_group="g1"),
    ]
    dag = build_dag(tasks)
    with pytest.raises(ParallelGroupConflict):
        topological_order(dag)


def test_parallel_group_conflict_not_cyclic_dependency() -> None:
    """I-SCH-5: ParallelGroupConflict is raised — NOT CyclicDependency — for group conflicts."""
    tasks = [
        _task("T-A", parallel_group="g1"),
        _task("T-B", depends_on=("T-A",), parallel_group="g1"),
    ]
    dag = build_dag(tasks)
    with pytest.raises(ParallelGroupConflict):
        topological_order(dag)
    # Confirm it does NOT raise CyclicDependency
    try:
        topological_order(dag)
    except ParallelGroupConflict:
        pass
    except CyclicDependency:
        pytest.fail("Should raise ParallelGroupConflict, not CyclicDependency")


def test_scheduler_pure_functions_deterministic() -> None:
    """I-SCH-3: build_dag and topological_order are pure — same inputs → same outputs."""
    tasks = [
        _task("T-A"),
        _task("T-B", depends_on=("T-A",)),
        _task("T-C", depends_on=("T-A",)),
    ]
    dag1 = build_dag(tasks)
    dag2 = build_dag(tasks)
    assert dag1 == dag2

    layers1 = topological_order(dag1)
    layers2 = topological_order(dag2)
    assert layers1 == layers2
