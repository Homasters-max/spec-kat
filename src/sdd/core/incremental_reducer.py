"""IncrementalReducer — BC-32-5 incremental state projection.

Wraps EventReducer to apply new events on top of a known base state.
All event-handling logic lives in EventReducer._fold(); this module
contains no dispatch logic of its own (I-STATE-REBUILD-1).

I-STATE-REBUILD-1:
    reduce(all_events) == apply_delta(EMPTY_STATE, all_events)
    reduce(all_events) == apply_delta(reduce(events[:k]), events[k:])  for any k.
"""

from __future__ import annotations

from sdd.domain.state.reducer import EMPTY_STATE, EventReducer, SDDState


class IncrementalReducer:
    """Applies a delta of new events onto an existing base state.

    Delegates entirely to EventReducer.reduce_incremental() — no event-handling
    logic is implemented here (I-HANDLER-PURE-1, I-STATE-REBUILD-1).
    """

    def __init__(self) -> None:
        self._reducer = EventReducer()

    def apply_delta(
        self,
        base: SDDState,
        new_events: list[dict[str, object]],
        strict_mode: bool = False,
    ) -> SDDState:
        """Apply new_events on top of base state.

        Precondition: new_events MUST be sorted by seq ASC (I-EL-13).
        """
        return self._reducer.reduce_incremental(base, new_events, strict_mode=strict_mode)

    def apply_delta_from_scratch(
        self,
        events: list[dict[str, object]],
        strict_mode: bool = False,
    ) -> SDDState:
        """Full replay via incremental path (I-STATE-REBUILD-1 verification helper).

        Equivalent to EventReducer().reduce(events) — used to verify that
        apply_delta(EMPTY_STATE, events) == reduce(events).
        """
        return self._reducer.reduce_incremental(EMPTY_STATE, events, strict_mode=strict_mode)
