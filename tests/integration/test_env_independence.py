"""Environment Independence Tests — I-ENV-1, I-ENV-2.

T-1006 recovery: this file was marked DONE in Phase 10 but never written.
Created during T-1317 final smoke validation.

I-ENV-1: sdd --help succeeds with minimal env dict (no PYTHONPATH).
I-ENV-2: sdd CLI exits non-zero with stderr output when sdd package is unimportable.

Phase 16 note: deprecated Pattern B adapters are archived (see ValidationReport_T-1317.md).
I-ENV-BOOT-1 (JSON schema compliance) was partial and specific to those adapters.
"""
from __future__ import annotations

import os
import subprocess
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
    """I-ENV-2: sdd CLI exits non-zero with stderr output when sdd package is unimportable.

    Phase 16: deprecated Pattern B adapters are archived; this test now verifies the
    sdd CLI itself exits non-zero when the sdd package cannot be imported.
    """
    # Shadow the real sdd package with a fake one that raises ImportError
    fake_sdd = tmp_path / "sdd"
    fake_sdd.mkdir()
    (fake_sdd / "__init__.py").write_text(
        'raise ImportError("fake sdd — package not installed")\n'
    )

    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    result = subprocess.run(
        ["sdd", "--help"],
        env=env,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, "Expected non-zero exit when sdd package not importable"
    assert result.stderr.strip(), "Expected error output on stderr when import fails"
