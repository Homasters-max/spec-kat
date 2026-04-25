"""BC-VR-0: ExecutionContext — stdlib-only kernel context tracking.

Invariants: I-EXEC-CONTEXT-1, I-KERNEL-WRITE-1.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator


class KernelContextError(Exception):
    """Raised when a kernel operation is called outside kernel_context."""


_EXECUTION_CTX: ContextVar[str | None] = ContextVar("_EXECUTION_CTX", default=None)


@contextmanager
def kernel_context(name: str) -> Generator[None, None, None]:
    token = _EXECUTION_CTX.set(name)
    try:
        yield
    finally:
        _EXECUTION_CTX.reset(token)


def assert_in_kernel(operation: str) -> None:
    ctx = _EXECUTION_CTX.get()
    if ctx != "execute_command":
        raise KernelContextError(
            f"{operation} called outside execute_command (ctx={ctx!r})"
        )


def current_execution_context() -> str | None:
    return _EXECUTION_CTX.get()
