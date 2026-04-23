"""hooks/log_bash.py — legacy stub: delegates to log_tool.py.

Invariants: I-HOOK-2, I-HOOKS-ISO
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    log_tool = Path(__file__).parent / "log_tool.py"
    subprocess.run(
        [sys.executable, str(log_tool)] + sys.argv[1:],
        check=False,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
