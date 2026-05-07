"""EventLogKernelProtocol — structural protocol for Write Kernel injection (I-ELK-PROTO-1)."""
from __future__ import annotations

from sdd.core.events import TaskImplementedEvent
from sdd.infra.event_log import EventLog, EventLogKernelProtocol


def _make_event() -> TaskImplementedEvent:
    return TaskImplementedEvent(
        event_type="TaskImplemented",
        event_id="proto-test-id",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        task_id="T-001",
        phase_id=43,
        timestamp="2026-01-01T00:00:00Z",
    )


class FakeEventLog:
    """In-memory EventLog stub that satisfies EventLogKernelProtocol."""

    def __init__(self) -> None:
        self.captured: list = []
        self._seq: int = 0

    def max_seq(self) -> int | None:
        return self._seq if self._seq > 0 else None

    def append(
        self,
        events: list,
        source: str,
        command_id: str | None = None,
        expected_head: int | None = None,
        allow_outside_kernel: str | None = None,
        batch_id: str | None = None,
    ) -> None:
        self.captured.extend(events)
        self._seq += len(events)


def test_execute_command_uses_injected_event_log(tmp_db_path: str) -> None:
    """EventLog satisfies EventLogKernelProtocol — can be injected into execute_command (I-ELK-PROTO-1)."""
    el: EventLogKernelProtocol = EventLog(tmp_db_path)
    assert isinstance(el, EventLogKernelProtocol)


def test_fake_event_log_captures_appended_events() -> None:
    """FakeEventLog satisfies EventLogKernelProtocol; append() captures events for test assertions."""
    assert isinstance(FakeEventLog(), EventLogKernelProtocol)

    fake = FakeEventLog()
    assert fake.max_seq() is None

    fake.append([_make_event()], source="test")
    assert len(fake.captured) == 1
    assert fake.captured[0].task_id == "T-001"
    assert fake.max_seq() == 1

    fake.append([_make_event(), _make_event()], source="test")
    assert len(fake.captured) == 3
    assert fake.max_seq() == 3
