from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
    from sdd.spatial.index import SpatialIndex
    from sdd.spatial.nodes import SpatialNode

_logger = logging.getLogger(__name__)

_NAV_SESSION_FILENAME = "nav_session.json"
_NAV_LOCK_FILENAME = "nav_session.lock"
_LOCK_TIMEOUT_SECS: float = 5.0
_LOCK_RETRY_INTERVAL: float = 0.05


# I-NAV-8: INTENT_CEILING is the single source of truth for max allowed mode per intent type.
MODE_ORDER: list[str] = ["POINTER", "SUMMARY", "SIGNATURE", "FULL"]

INTENT_CEILING: dict[str, str] = {
    "explore":     "SUMMARY",
    "locate":      "SUMMARY",
    "analyze":     "SIGNATURE",
    "code_write":  "FULL",
    "code_modify": "FULL",
}


def _modes_up_to(ceiling: str) -> frozenset[str]:
    return frozenset(MODE_ORDER[: MODE_ORDER.index(ceiling) + 1])


@dataclass(frozen=True)
class NavigationIntent:
    type: Literal["explore", "locate", "analyze", "code_write", "code_modify"]

    def ceiling(self) -> str:
        """I-NAV-8: single source of truth for max allowed mode."""
        return INTENT_CEILING[self.type]

    def allowed_modes(self) -> frozenset[str]:
        return _modes_up_to(self.ceiling())


@dataclass(frozen=True)
class DenialTrace:
    """Structured denial with specific violated invariant(s)."""
    mode:     str         # requested mode that was denied
    violated: list[str]   # violated invariants e.g. ["I-NAV-1"]
    reason:   str         # "summary_required"|"step_limit_exceeded"|
                          # "code_intent_required"|"intent_ceiling_exceeded"


@dataclass(frozen=True)
class AllowedOperations:
    modes:  frozenset[str]       # subset of {POINTER, SUMMARY, SIGNATURE, FULL}
    denial: DenialTrace | None   # None if requested mode is allowed


# I-NAV-8 REFORM: constraints as data (table), not if-chain.
# Each entry: (mode_guard, predicate, violated_invariants, reason)
# predicate(session, node_id, intent) → True means DENIED
_FULL_CONSTRAINTS: list[tuple[
    str,
    Callable[["NavigationSession", str, NavigationIntent | None], bool],
    list[str],
    str,
]] = [
    (
        "FULL",
        lambda s, n, i: not s.can_load_full(n),
        ["I-NAV-1"],
        "summary_required",
    ),
    (
        "FULL",
        lambda s, n, i: s.full_load_count_per_step.get(s.step_id, 0) >= 1,
        ["I-NAV-3", "I-NAV-6"],
        "step_limit_exceeded",
    ),
    (
        "FULL",
        lambda s, n, i: i is None or i.type not in ("code_write", "code_modify"),
        ["I-NAV-5"],
        "code_intent_required",
    ),
]


def resolve_action(
    intent: NavigationIntent | None,
    session: "NavigationSession",
    node_id: str,
    requested_mode: str,
) -> AllowedOperations:
    """I-NAV-8: intent ceiling is single source of truth (INTENT_CEILING table).
    Session constraints applied via _FULL_CONSTRAINTS registry (no if-chain)."""
    ceiling_modes = intent.allowed_modes() if intent else _modes_up_to("SUMMARY")

    if requested_mode not in ceiling_modes:
        return AllowedOperations(
            modes=ceiling_modes,
            denial=DenialTrace(
                mode=requested_mode,
                violated=["I-NAV-8"] if intent else ["I-NAV-7"],
                reason="intent_ceiling_exceeded" if intent else "code_intent_required",
            ),
        )

    for mode_guard, predicate, violated, reason in _FULL_CONSTRAINTS:
        if requested_mode == mode_guard and predicate(session, node_id, intent):
            return AllowedOperations(
                modes=ceiling_modes - {mode_guard},
                denial=DenialTrace(mode=mode_guard, violated=violated, reason=reason),
            )

    return AllowedOperations(modes=ceiling_modes, denial=None)


@dataclass
class NavigationSession:
    """In-memory session state for Navigation Protocol enforcement (I-NAV-1..6, I-NAV-9)."""
    step_id:                  int
    resolved_nodes:           set[str] = field(default_factory=set)
    loaded_modes:             dict[str, str] = field(default_factory=dict)
    full_load_count_per_step: dict[int, int] = field(default_factory=dict)
    term_searched:            bool = False
    intent:                   NavigationIntent | None = None

    def can_load_full(self, node_id: str) -> bool:
        """I-NAV-1: SUMMARY or SIGNATURE must precede FULL."""
        return self.loaded_modes.get(node_id) in ("SUMMARY", "SIGNATURE")

    def can_load_full_step(self, intent: NavigationIntent | None = None) -> bool:
        """I-NAV-3/5/6: max 1 FULL per step_id; only for code_write/code_modify."""
        if self.full_load_count_per_step.get(self.step_id, 0) >= 1:
            return False
        if intent is None or intent.type not in ("code_write", "code_modify"):
            return False
        return True

    def next_step(self) -> None:
        """I-NAV-6/9: explicit step boundary; resets per-step state."""
        self.step_id += 1
        self.term_searched = False
        self.intent = None

    def record_load(self, node_id: str, mode: str) -> None:
        self.resolved_nodes.add(node_id)
        self.loaded_modes[node_id] = mode
        if mode == "FULL":
            self.full_load_count_per_step[self.step_id] = (
                self.full_load_count_per_step.get(self.step_id, 0) + 1
            )


# ---------------------------------------------------------------------------
# Session persistence (I-NAV-SESSION-1, I-SESSION-2)
# ---------------------------------------------------------------------------

class SessionLockTimeout(RuntimeError):
    """Raised when nav_session.lock cannot be acquired within timeout."""
    reason = "session_lock_timeout"


def _nav_session_path(sdd_root: str) -> Path:
    return Path(sdd_root) / "state" / _NAV_SESSION_FILENAME


def _nav_lock_path(sdd_root: str) -> Path:
    return Path(sdd_root) / "state" / _NAV_LOCK_FILENAME


@contextlib.contextmanager
def _session_lock(lock_path: str, timeout_secs: float = _LOCK_TIMEOUT_SECS):
    """Exclusive advisory lock for nav_session.json (I-SESSION-2).

    Uses non-blocking flock with retry loop; raises SessionLockTimeout after
    timeout_secs if lock cannot be acquired.
    """
    p = Path(lock_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_secs
    with open(p, "w") as lf:
        while True:
            try:
                fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise SessionLockTimeout("session_lock_timeout")
                time.sleep(_LOCK_RETRY_INTERVAL)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def _serialize_session(session: NavigationSession) -> dict:
    return {
        "session_id": str(uuid.uuid4()),
        "step_id": session.step_id,
        "resolved_nodes": sorted(session.resolved_nodes),
        "loaded_modes": session.loaded_modes,
        "full_load_count_per_step": {
            str(k): v for k, v in session.full_load_count_per_step.items()
        },
        "intent": session.intent.type if session.intent else None,
        "term_searched": session.term_searched,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _deserialize_session(data: dict) -> NavigationSession:
    intent = None
    if data.get("intent"):
        intent = NavigationIntent(type=data["intent"])  # type: ignore[arg-type]
    full_count = {
        int(k): v
        for k, v in data.get("full_load_count_per_step", {}).items()
    }
    return NavigationSession(
        step_id=int(data.get("step_id", 0)),
        resolved_nodes=set(data.get("resolved_nodes", [])),
        loaded_modes=dict(data.get("loaded_modes", {})),
        full_load_count_per_step=full_count,
        term_searched=bool(data.get("term_searched", False)),
        intent=intent,
    )


def load_session(sdd_root: str) -> NavigationSession:
    """Load NavigationSession from nav_session.json (I-NAV-SESSION-1).

    Missing file → fresh session (not an error).
    Invalid JSON → log warning + fresh session (corruption recovery).
    """
    session_path = _nav_session_path(sdd_root)
    lock_path = str(_nav_lock_path(sdd_root))
    session_path.parent.mkdir(parents=True, exist_ok=True)
    if not session_path.exists():
        return NavigationSession(step_id=0)
    with _session_lock(lock_path):
        try:
            data = json.loads(session_path.read_text())
            return _deserialize_session(data)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            _logger.warning(
                "nav_session.json is invalid or corrupt; starting fresh session"
            )
            return NavigationSession(step_id=0)


def save_session(session: NavigationSession, sdd_root: str) -> None:
    """Atomically persist NavigationSession to nav_session.json (I-NAV-SESSION-1).

    Writes to a temp file then uses os.replace for atomicity.
    """
    session_path = _nav_session_path(sdd_root)
    lock_path = str(_nav_lock_path(sdd_root))
    session_path.parent.mkdir(parents=True, exist_ok=True)
    with _session_lock(lock_path):
        data = _serialize_session(session)
        fd, tmp = tempfile.mkstemp(dir=session_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, session_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def clear_session(sdd_root: str) -> None:
    """Remove nav_session.json (called by sdd nav-session clear)."""
    try:
        _nav_session_path(sdd_root).unlink()
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Navigator (BC-18-3)
# ---------------------------------------------------------------------------

# I-SI-2: deterministic kind priority for fuzzy sort
_KIND_PRIORITY: dict[str, int] = {
    "TERM": 0, "COMMAND": 1, "TASK": 2, "INVARIANT": 3,
    "GUARD": 4, "REDUCER": 5, "EVENT": 6, "FILE": 7,
}


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for ch in a:
        curr = [prev[0] + 1]
        for j, d in enumerate(b):
            curr.append(min(prev[j] + (0 if ch == d else 1), curr[-1] + 1, prev[j + 1] + 1))
        prev = curr
    return prev[-1]


def _search_keys(node: "SpatialNode") -> list[str]:
    """I-FUZZY-1: search key by kind; FILE→basename without ext; TERM includes aliases."""
    suffix = node.node_id.split(":", 1)[-1]
    if node.kind == "FILE":
        return [Path(suffix).stem]
    if node.kind == "TERM":
        return [suffix] + list(node.aliases)
    return [suffix]


class Navigator:
    """Deterministic node resolver over SpatialIndex (I-SI-2, I-SI-3, I-FUZZY-1, I-SEARCH-2)."""

    def __init__(
        self,
        index: "SpatialIndex",
        session: NavigationSession | None = None,
        project_root: str | None = None,
    ) -> None:
        self._index = index
        self._session = session
        self._project_root = project_root

    def resolve(
        self,
        node_id: str,
        mode: str = "SUMMARY",
        intent: NavigationIntent | None = None,
    ) -> dict:
        """I-SI-2: same id+index → same output. I-SI-3: no open() except FULL FILE."""
        if node_id not in self._index.nodes:
            return self.not_found_response(node_id)

        node = self._index.nodes[node_id]

        if self._session is not None:
            allowed = resolve_action(intent, self._session, node_id, mode)
            if allowed.denial is not None:
                d = allowed.denial
                return {
                    "status": "nav_invariant_violation",
                    "invariant": d.violated[0] if d.violated else "I-NAV-8",
                    "denial": {
                        "mode": d.mode,
                        "violated": d.violated,
                        "reason": d.reason,
                    },
                    "node_id": node_id,
                    "message": f"{d.reason}: {d.violated[0] if d.violated else ''}",
                }

        return self._build_response(node, mode)

    def _build_response(self, node: "SpatialNode", mode: str) -> dict:
        response: dict = {
            "node_id": node.node_id,
            "kind": node.kind,
            "label": node.label,
            "path": node.path,
        }
        if mode == "POINTER":
            return response

        response["summary"] = node.summary
        response["git_hash"] = node.git_hash
        response["indexed_at"] = node.indexed_at
        if mode == "SUMMARY":
            return response

        response["signature"] = node.signature
        if mode == "SIGNATURE":
            return response

        # FULL — I-SI-3: filesystem access only here
        response["meta"] = node.meta
        if node.kind == "TERM":
            response["definition"] = node.definition
            response["aliases"] = list(node.aliases)
            response["links"] = list(node.links)
        if node.kind == "FILE" and node.path:
            try:
                file_path = Path(node.path)
                if not file_path.is_absolute() and self._project_root:
                    file_path = Path(self._project_root) / file_path
                response["full_text"] = file_path.read_text()
            except OSError:
                response["full_text"] = None
        return response

    def search(
        self,
        query: str,
        kind: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """I-SEARCH-2: collect → sort → limit → render. I-FUZZY-1: search key based."""
        query_lower = query.lower()

        # Step 1: collect candidates with distance score
        scored: list[tuple[int, int, str]] = []
        for node in self._index.nodes.values():
            if kind is not None and node.kind != kind:
                continue
            keys = _search_keys(node)
            best = min(_levenshtein(query_lower, k.lower()) for k in keys)
            if best <= 2:
                kp = _KIND_PRIORITY.get(node.kind, 99)
                scored.append((best, kp, node.node_id))

        # Step 2: deterministic sort (distance, kind_priority, node_id lex)
        scored.sort()

        # Step 3: limit before render (I-SEARCH-2)
        scored = scored[:limit]

        # Step 4: render
        results = []
        for distance, _, nid in scored:
            node = self._index.nodes[nid]
            results.append({
                "node_id": node.node_id,
                "kind": node.kind,
                "label": node.label,
                "score": max(0.0, 1.0 - distance / max(len(query_lower), 1)),
            })
        return results

    def not_found_response(self, query: str) -> dict:
        """Anti-hallucination response; did_you_mean always present (may be empty)."""
        query_lower = query.lower()
        scored: list[tuple[int, int, str]] = []
        for node in self._index.nodes.values():
            keys = _search_keys(node)
            best = min(_levenshtein(query_lower, k.lower()) for k in keys)
            kp = _KIND_PRIORITY.get(node.kind, 99)
            scored.append((best, kp, node.node_id))
        scored.sort()
        did_you_mean = [nid for _, _, nid in scored[:5]]
        return {
            "status": "not_found",
            "must_not_guess": True,
            "query": query,
            "did_you_mean": did_you_mean,
        }
