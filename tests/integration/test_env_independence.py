"""Environment Independence Tests — I-ENV-1, I-ENV-2, I-ENV-BOOT-1 (partial).

T-1006 recovery: this file was marked DONE in Phase 10 but never written.
Created during T-1317 final smoke validation.

I-ENV-1: sdd --help succeeds with minimal env dict (no PYTHONPATH).
I-ENV-2: Adapter ImportError outputs "pip install -e ." message to stderr.
I-ENV-BOOT-1: Adapter ImportError output is structured JSON (partial — deprecated
              adapters use "error" key, not "error_type"; see ValidationReport T-1317).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_sdd_help_minimal_env():
    """I-ENV-1: sdd --help exits 0 with minimal env (PATH/HOME/VIRTUAL_ENV/LANG/LC_ALL only)."""
    env = {
        k: os.environ[k]
        for k in ("PATH", "HOME", "VIRTUAL_ENV", "LANG", "LC_ALL")
        if k in os.environ
    }
    result = subprocess.run(
        ["sdd", "--help"],
        env=env,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"sdd --help failed: {result.stderr}"
    assert "sdd" in result.stdout.lower(), "Expected 'sdd' in help output"


def test_adapter_import_error_message(tmp_path):
    """I-ENV-2 / I-ENV-BOOT-1 (partial): deprecated Pattern B adapter with broken import
    outputs JSON to stderr containing 'pip install -e .' and exits non-zero.

    Note: deprecated adapters use {"error": "SDD_IMPORT_FAILED"} schema (exit 2).
    Full I-ENV-BOOT-1 compliance (error_type/exit_code fields) is not present in
    the archived adapters — documented in ValidationReport_T-1317.md.
    """
    # Shadow the real sdd package with a fake one that raises ImportError
    fake_sdd = tmp_path / "sdd"
    fake_sdd.mkdir()
    (fake_sdd / "__init__.py").write_text(
        'raise ImportError("fake sdd — package not installed")\n'
    )

    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    result = subprocess.run(
        ["python3", ".sdd/_deprecated_tools/check_scope.py", "--help"],
        env=env,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, "Expected non-zero exit when sdd package not importable"

    stderr = result.stderr.strip()
    assert stderr, "Expected JSON error on stderr"

    payload = json.loads(stderr)  # I-ENV-BOOT-1: must be valid JSON
    assert "pip install -e ." in payload.get("message", ""), (
        f"Expected 'pip install -e .' in error message, got: {payload}"
    )
