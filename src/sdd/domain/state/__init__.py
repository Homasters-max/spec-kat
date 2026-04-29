"""BC-STATE public API — Spec_v2 §2."""

from sdd.core.events import StateDerivationCompletedEvent
from sdd.domain.state.init_state import init_state
from sdd.core.errors import UnknownEventType
from sdd.domain.state.reducer import (
    EMPTY_STATE,
    EventReducer,
    ReducerDiagnostics,
    SDDState,
    compute_state_hash,
    reduce,
    reduce_with_diagnostics,
)
from sdd.domain.state.sync import sync_state
from sdd.domain.state.yaml_state import read_state, write_state

__all__ = [
    "SDDState",
    "EMPTY_STATE",
    "ReducerDiagnostics",
    "EventReducer",
    "UnknownEventType",
    "compute_state_hash",
    "reduce",
    "reduce_with_diagnostics",
    "read_state",
    "write_state",
    "sync_state",
    "init_state",
    "StateDerivationCompletedEvent",
]
