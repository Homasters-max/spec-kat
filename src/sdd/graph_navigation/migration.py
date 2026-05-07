"""BC-36-5 legacy migration gate (Spec_v52 §3).

I-CTX-MIGRATION-1..4: migration_complete() is the hard DoD gate for Phase 52.
After returning True, direct FS reads in build_context.py violate I-GRAPH-FS-ROOT-1.
"""
from __future__ import annotations

import re
from pathlib import Path

_CLI_HANDLERS = ["resolve.py", "trace.py", "explain.py", "invariant.py"]

_RUNTIME_PATTERN = re.compile(r"ContextRuntime")
_BUILD_CONTEXT_CALLER = re.compile(
    r"from sdd\.context\.build_context\b"
    r"|from sdd\.context import[^;#\n]*build_context"
)


def migration_complete() -> bool:
    """
    Проверяет оба критерия I-LEGACY-FS-EXCEPTION-1:
    1. Все BC-36 CLI handlers маршрутизируют через ContextRuntime.
    2. build_context.py имеет 0 прямых callers вне context_legacy/.

    Returns True → migration window формально закрыт.
    """
    return _handlers_use_runtime() and _no_external_build_context_callers()


def _handlers_use_runtime() -> bool:
    cli_dir = Path(__file__).parent / "cli"
    for name in _CLI_HANDLERS:
        handler = cli_dir / name
        if not handler.exists():
            return False
        if not _RUNTIME_PATTERN.search(handler.read_text(encoding="utf-8")):
            return False
    return True


def _no_external_build_context_callers() -> bool:
    sdd_src = Path(__file__).parent.parent
    for py_file in sdd_src.rglob("*.py"):
        parts = py_file.relative_to(sdd_src).parts
        # context/ owns build_context.py; context_legacy/ is the allowed new home
        if parts[0] in ("context", "context_legacy"):
            continue
        if _BUILD_CONTEXT_CALLER.search(py_file.read_text(encoding="utf-8")):
            return False
    return True
