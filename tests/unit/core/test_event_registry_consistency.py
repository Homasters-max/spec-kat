"""I-ST-10 / I-EREG-1: EventReducer._KNOWN_NO_HANDLER is derived, not duplicated.

Spec_v39 BC-39-3.
"""
from sdd.core.events import V1_L1_EVENT_TYPES
from sdd.domain.state.reducer import EventReducer


def test_i_st_10_all_event_types_classified():
    """I-ST-10: V1_L1_EVENT_TYPES == _KNOWN_NO_HANDLER ∪ _EVENT_SCHEMA.keys()."""
    classified = EventReducer._KNOWN_NO_HANDLER | frozenset(EventReducer._EVENT_SCHEMA.keys())
    missing = V1_L1_EVENT_TYPES - classified
    extra = classified - V1_L1_EVENT_TYPES
    assert not missing, f"Events in V1_L1_EVENT_TYPES but not classified: {missing}"
    assert not extra, f"Events classified but not in V1_L1_EVENT_TYPES: {extra}"


def test_i_ereg_1_known_no_handler_is_derived():
    """I-EREG-1: _KNOWN_NO_HANDLER MUST equal V1_L1_EVENT_TYPES - _EVENT_SCHEMA.keys().

    Verifies the derived relationship — no independent static literal.
    """
    expected = V1_L1_EVENT_TYPES - frozenset(EventReducer._EVENT_SCHEMA.keys())
    assert EventReducer._KNOWN_NO_HANDLER == expected, (
        f"_KNOWN_NO_HANDLER is not derived from V1_L1_EVENT_TYPES - _EVENT_SCHEMA.keys(). "
        f"Diff: {EventReducer._KNOWN_NO_HANDLER.symmetric_difference(expected)}"
    )


def test_i_st_10_missing_event_is_detectable():
    """I-ST-10: adding a type to V1_L1_EVENT_TYPES without classifying it is detectable.

    Simulates the defect that BC-39-2 prevents: a new event type present in V1_L1_EVENT_TYPES
    but absent from both _EVENT_SCHEMA and _KNOWN_NO_HANDLER would be caught by
    test_i_st_10_all_event_types_classified.
    """
    fake_type = "_SimulatedUnclassifiedEvent_v39"
    extended_v1 = V1_L1_EVENT_TYPES | frozenset({fake_type})
    classified = EventReducer._KNOWN_NO_HANDLER | frozenset(EventReducer._EVENT_SCHEMA.keys())
    missing = extended_v1 - classified
    assert fake_type in missing, (
        "Simulation failed: a new unclassified type was not detected as missing. "
        "I-ST-10 guard is ineffective."
    )
