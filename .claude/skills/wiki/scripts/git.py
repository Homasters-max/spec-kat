from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from state import read_ingest_log


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GitRepo:
    def __init__(self, vault_root: Path) -> None:
        self.vault_root = vault_root

    def pending_raw_files(self) -> list[Path]:
        result = subprocess.run(
            ["git", "status", "--porcelain", "-u", "raw/"],
            cwd=self.vault_root,
            capture_output=True,
            text=True,
            check=True,
        )
        raw_candidates: list[Path] = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            xy = line[:2]
            rel = line[3:].strip()
            # untracked (??) or modified in worktree (second char M or ?)
            if xy[1] in ("M", "?") or xy[0] in ("M", "A", "?"):
                p = self.vault_root / rel
                if p.exists() and p.is_file():
                    raw_candidates.append(p)

        known_sha256s = {e.sha256 for e in read_ingest_log(self.vault_root)}
        return [p for p in raw_candidates if _sha256(p) not in known_sha256s]

    def commit(self, message: str, files: list[Path]) -> None:
        rel_files = [str(p.relative_to(self.vault_root)) for p in files]
        subprocess.run(
            ["git", "add", "--"] + rel_files,
            cwd=self.vault_root,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.vault_root,
            check=True,
        )
