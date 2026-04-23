"""DAG builder and topological ordering for TaskSet — Spec_v3 §4.10."""
from __future__ import annotations

from dataclasses import dataclass

from sdd.core.errors import CyclicDependency, MissingContext, ParallelGroupConflict
from sdd.domain.tasks.parser import Task


@dataclass(frozen=True)
class TaskNode:
    task_id: str
    depends_on: tuple[str, ...]
    parallel_group: str | None


def build_dag(tasks: list[Task]) -> dict[str, TaskNode]:
    """Build dependency graph from task list.

    Pure function (I-SCH-3). tasks=[] → returns {}.
    Raises CyclicDependency if depends_on references form a cycle (I-SCH-4).
    Raises MissingContext if depends_on references an unknown task_id (I-SCH-4).
    """
    if not tasks:
        return {}

    known = {t.task_id for t in tasks}
    nodes: dict[str, TaskNode] = {}

    for t in tasks:
        for dep in t.depends_on:
            if dep not in known:
                raise MissingContext(
                    f"Task {t.task_id} depends_on unknown task_id: {dep!r}"
                )
        nodes[t.task_id] = TaskNode(
            task_id=t.task_id,
            depends_on=t.depends_on,
            parallel_group=t.parallel_group,
        )

    # Cycle detection via DFS
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in nodes}

    def _dfs(tid: str) -> None:
        color[tid] = GRAY
        for dep in nodes[tid].depends_on:
            if color[dep] == GRAY:
                raise CyclicDependency(
                    f"Cycle detected involving task {tid!r} → {dep!r}"
                )
            if color[dep] == WHITE:
                _dfs(dep)
        color[tid] = BLACK

    for tid in nodes:
        if color[tid] == WHITE:
            _dfs(tid)

    return nodes


def topological_order(dag: dict[str, TaskNode]) -> list[list[str]]:
    """Return execution layers for the dependency graph.

    Pure function (I-SCH-3). dag={} → returns [].
    I-SCH-1: no dependency-order violations (verified by post-check).
    I-SCH-2: every task_id appears exactly once.
    I-SCH-5: same parallel_group → same layer (or ParallelGroupConflict).
    I-SCH-6: parallel_group constraint never silently ignored.
    Raises CyclicDependency if cycle detected during ordering (I-SCH-1).
    Raises ParallelGroupConflict if parallel_group + depends_on conflict (I-SCH-6).
    """
    if not dag:
        return []

    # Kahn's algorithm: compute in-degrees
    in_degree: dict[str, int] = {tid: 0 for tid in dag}
    for node in dag.values():
        for dep in node.depends_on:
            in_degree[node.task_id] += 1

    # Recompute correctly: count incoming edges
    in_degree = {tid: 0 for tid in dag}
    for node in dag.values():
        for dep in node.depends_on:
            in_degree[node.task_id] = in_degree.get(node.task_id, 0)
    # Build adjacency for in-degree
    in_degree = {tid: 0 for tid in dag}
    for node in dag.values():
        for dep in node.depends_on:
            # node.task_id depends on dep → dep must come first (dep → node edge)
            pass
    # Simplest: count how many of a task's depends_on must precede it
    in_degree = {tid: len(dag[tid].depends_on) for tid in dag}

    # Layer-by-layer BFS
    layers: list[list[str]] = []
    satisfied: set[str] = set()

    remaining = set(dag.keys())

    while remaining:
        # Tasks ready: all depends_on in satisfied
        ready = sorted(
            tid for tid in remaining
            if all(dep in satisfied for dep in dag[tid].depends_on)
        )
        if not ready:
            raise CyclicDependency(
                f"Cycle detected in dependency graph; unresolved: {sorted(remaining)}"
            )

        # Handle parallel_group co-location:
        # For each task in ready, if it has a parallel_group, pull ALL group members
        # that are NOT yet satisfied. If any group member is not yet ready → conflict.
        layer_set: set[str] = set()
        for tid in ready:
            layer_set.add(tid)
            pg = dag[tid].parallel_group
            if pg is not None:
                for other_tid, other_node in dag.items():
                    if other_node.parallel_group == pg and other_tid not in satisfied:
                        # Check if other_tid is ready
                        if not all(dep in satisfied for dep in dag[other_tid].depends_on):
                            raise ParallelGroupConflict(
                                f"{other_tid} and {tid} share group {pg!r} but "
                                f"{other_tid} cannot be co-located: unsatisfied deps "
                                f"{[d for d in dag[other_tid].depends_on if d not in satisfied]}"
                            )
                        layer_set.add(other_tid)

        layer = sorted(layer_set)
        layers.append(layer)
        satisfied.update(layer)
        remaining -= layer_set

    # Post-check I-SCH-1: verify no layer contains a task whose dep is in the same/later layer
    placed: dict[str, int] = {}
    for i, layer in enumerate(layers):
        for tid in layer:
            placed[tid] = i
    for tid, node in dag.items():
        for dep in node.depends_on:
            if placed[dep] >= placed[tid]:
                raise CyclicDependency(
                    f"Dependency order violation: {tid!r} in layer {placed[tid]} "
                    f"but depends on {dep!r} in layer {placed[dep]}"
                )

    # Post-check I-SCH-2: every task_id appears exactly once
    all_placed = [tid for layer in layers for tid in layer]
    if len(all_placed) != len(dag):
        raise CyclicDependency("Not all tasks placed — internal error")

    return layers
