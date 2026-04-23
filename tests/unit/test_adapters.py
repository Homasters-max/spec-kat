"""tests/unit/test_adapters.py — Legacy boundary invariant I-LEGACY-0."""
from __future__ import annotations

import subprocess
from pathlib import Path

SRC_DIR = Path("src/sdd")


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def test_no_tools_imported_in_src() -> None:
    """Legacy boundary I-LEGACY-0: src/sdd/* must not import legacy tool packages."""
    for pattern in ("from .sdd.tools", "import .sdd.tools"):
        result = _run(["grep", "-r", pattern, str(SRC_DIR)])
        assert result.stdout.strip() == "", (
            f"Found forbidden import {pattern!r} in src/sdd/:\n{result.stdout}"
        )
