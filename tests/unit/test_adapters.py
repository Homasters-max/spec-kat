"""tests/unit/test_adapters.py — Adapter invariants I-ADAPT-1..4, I-HOOK-API-2."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(".sdd/_deprecated_tools")
SRC_DIR = Path("src/sdd")

# Adapter files converted in Phase 8 (T-811 + T-812 outputs).
# Legacy infra scripts (derive_state.py, guard_runner.py, etc.) are out of scope.
_T811 = ["log_tool.py", "update_state.py", "validate_invariants.py",
         "query_events.py", "metrics_report.py", "report_error.py", "sync_state.py"]
_T812 = ["phase_guard.py", "task_guard.py", "check_scope.py", "norm_guard.py",
         "build_context.py", "record_metric.py", "senar_audit.py", "log_bash.py"]
ADAPTER_FILES = [TOOLS_DIR / name for name in _T811 + _T812]

PATTERN_B = [
    TOOLS_DIR / "log_tool.py",
    TOOLS_DIR / "log_bash.py",
    TOOLS_DIR / "phase_guard.py",
    TOOLS_DIR / "task_guard.py",
    TOOLS_DIR / "check_scope.py",
    TOOLS_DIR / "norm_guard.py",
    TOOLS_DIR / "build_context.py",
    TOOLS_DIR / "record_metric.py",
    TOOLS_DIR / "senar_audit.py",
]


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def test_no_syspath_in_adapters() -> None:
    """I-ADAPT-1: no sys.path manipulation in any Phase-8 adapter file."""
    matches = []
    for adapter in ADAPTER_FILES:
        if "sys.path" in adapter.read_text(encoding="utf-8"):
            matches.append(str(adapter))
    assert not matches, f"sys.path found in adapters: {matches}"


def test_deprecated_comment_present() -> None:
    """I-ADAPT-1: each Phase-8 adapter has # DEPRECATED immediately after the shebang."""
    for adapter in ADAPTER_FILES:
        lines = adapter.read_text(encoding="utf-8").splitlines()
        non_shebang = [ln for ln in lines if not ln.startswith("#!")]
        assert non_shebang, f"{adapter.name}: no non-shebang lines"
        assert non_shebang[0].startswith("# DEPRECATED"), (
            f"{adapter.name}: first non-shebang line not # DEPRECATED: {non_shebang[0]!r}"
        )


def test_log_tool_is_pattern_b() -> None:
    """I-ADAPT-1: log_tool.py uses Pattern B (direct import, no subprocess delegation)."""
    source = (TOOLS_DIR / "log_tool.py").read_text(encoding="utf-8")
    assert "subprocess" not in source, "log_tool.py must not use subprocess (Pattern B)"
    assert "from sdd." in source, "log_tool.py must directly import from sdd package"


def test_update_state_is_pattern_a() -> None:
    """I-ADAPT-4: update_state.py uses Pattern A (subprocess.call + sys.exit(code))."""
    source = (TOOLS_DIR / "update_state.py").read_text(encoding="utf-8")
    assert "subprocess.call" in source, "update_state.py must use subprocess.call (Pattern A)"
    assert "sys.exit(code)" in source, "update_state.py must forward exit code via sys.exit(code)"


def test_update_state_help_parity() -> None:
    """I-ADAPT-2: python3 update_state.py --help output matches sdd --help."""
    adapter = _run(["python3", str(TOOLS_DIR / "update_state.py"), "--help"])
    direct = _run(["sdd", "--help"])
    assert adapter.returncode == direct.returncode
    assert adapter.stdout == direct.stdout


def test_query_events_help_parity() -> None:
    """I-ADAPT-2: python3 query_events.py --help output matches sdd query-events --help."""
    adapter = _run(["python3", str(TOOLS_DIR / "query_events.py"), "--help"])
    direct = _run(["sdd", "query-events", "--help"])
    assert adapter.returncode == direct.returncode
    assert adapter.stdout == direct.stdout


def test_metrics_report_help_parity() -> None:
    """I-ADAPT-2: python3 metrics_report.py --help output matches sdd metrics-report --help."""
    adapter = _run(["python3", str(TOOLS_DIR / "metrics_report.py"), "--help"])
    direct = _run(["sdd", "metrics-report", "--help"])
    assert adapter.returncode == direct.returncode
    assert adapter.stdout == direct.stdout


def test_pattern_b_structured_error_on_import_failure(tmp_path: Path) -> None:
    """I-ADAPT-3: Pattern B adapters emit JSON {error: SDD_IMPORT_FAILED} on stderr + exit 2."""
    fake_sdd = tmp_path / "sdd"
    fake_sdd.mkdir()
    (fake_sdd / "__init__.py").write_text("raise ImportError('fake sdd not installed')\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)

    for adapter in PATTERN_B:
        result = subprocess.run(
            [sys.executable, str(adapter)],
            capture_output=True, text=True, env=env, input="",
        )
        assert result.returncode == 2, (
            f"{adapter.name}: expected exit 2, got {result.returncode}. stderr={result.stderr!r}"
        )
        err = json.loads(result.stderr.strip())
        assert err.get("error") == "SDD_IMPORT_FAILED", f"{adapter.name}: {err}"
        assert "run: pip install -e ." in err.get("message", ""), f"{adapter.name}: {err}"


def test_pattern_a_exit_code_passthrough() -> None:
    """I-ADAPT-4: Pattern A adapter passes through the subprocess exit code unchanged."""
    direct = _run(["sdd", "--version"])
    adapter = _run(["python3", str(TOOLS_DIR / "update_state.py"), "--version"])
    assert adapter.returncode == direct.returncode


def test_hook_warns_on_positional_argv() -> None:
    """I-HOOK-API-2: log_bash.py emits WARNING to stderr when called with positional args."""
    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "log_bash.py"), "some_positional_arg"],
        capture_output=True, text=True, input="", timeout=10,
    )
    assert "WARNING" in result.stderr, f"Expected WARNING in stderr:\n{result.stderr}"
    assert "I-HOOK-API-2" in result.stderr, f"Expected I-HOOK-API-2 in stderr:\n{result.stderr}"
    assert "positional argv ignored" in result.stderr, f"Expected message in stderr:\n{result.stderr}"


def test_no_tools_imported_in_src() -> None:
    """Legacy boundary I-LEGACY-0: src/sdd/* must not import from .sdd/_deprecated_tools."""
    for pattern in ("from .sdd.tools", "import .sdd.tools"):
        result = _run(["grep", "-r", pattern, str(SRC_DIR)])
        assert result.stdout.strip() == "", (
            f"Found forbidden import {pattern!r} in src/sdd/:\n{result.stdout}"
        )
