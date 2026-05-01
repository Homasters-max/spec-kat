from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

from models import ApplyResult, PageType, RewriteOp, WikiDiff

_PAGE_TYPES: tuple[PageType, ...] = ("idea", "pattern", "tool")


class WikiRepo:
    def __init__(self, vault_root: Path) -> None:
        self.vault_root = vault_root

    def _page_path(self, page_id: str, page_type: PageType) -> Path:
        return self.vault_root / "wiki" / page_type / f"{page_id}.md"

    def _find_page_path(self, page_id: str) -> Path | None:
        for pt in _PAGE_TYPES:
            p = self._page_path(page_id, pt)
            if p.exists():
                return p
        return None

    def load_page(self, page_id: str) -> str | None:
        path = self._find_page_path(page_id)
        return path.read_text(encoding="utf-8") if path else None

    def list_pages(self, type: PageType | None = None) -> list[str]:
        types: tuple[PageType, ...] = (type,) if type else _PAGE_TYPES
        pages: list[str] = []
        for pt in types:
            d = self.vault_root / "wiki" / pt
            if d.exists():
                pages.extend(sorted(p.stem for p in d.glob("*.md")))
        return pages

    def page_size(self, page_id: str) -> int:
        content = self.load_page(page_id)
        return len(content) if content is not None else 0

    def create_page(self, page_id: str, page_type: PageType, content: str) -> ApplyResult:
        if "." in page_id:
            raise ValueError(f"page_id must not contain dots: {page_id!r}")
        if self._find_page_path(page_id) is not None:
            raise ValueError(f"page already exists: {page_id!r}")
        path = self._page_path(page_id, page_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ApplyResult(success=True, conflict=False, applied_lines=content.count("\n") + 1)

    def apply_diff(self, diff: WikiDiff) -> ApplyResult:
        path = self._find_page_path(diff.page_id)
        if path is None:
            return ApplyResult(success=False, conflict=True, applied_lines=0)

        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest() != diff.base_sha256:
            return ApplyResult(success=False, conflict=True, applied_lines=0)

        with tempfile.NamedTemporaryFile(suffix=".patch", mode="w", encoding="utf-8", delete=False) as tmp:
            tmp.write(diff.unified_diff)
            patch_file = Path(tmp.name)

        try:
            result = subprocess.run(
                ["patch", "--no-backup-if-mismatch", str(path), str(patch_file)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                path.write_bytes(original)
                return ApplyResult(success=False, conflict=True, applied_lines=0)
            applied = sum(1 for ln in diff.unified_diff.splitlines() if ln.startswith(("+", "-")) and not ln.startswith(("---", "+++")))
            return ApplyResult(success=True, conflict=False, applied_lines=applied)
        finally:
            patch_file.unlink(missing_ok=True)

    def rewrite_page(self, op: RewriteOp) -> ApplyResult:
        path = self._find_page_path(op.page_id)
        if path is None:
            return ApplyResult(success=False, conflict=True, applied_lines=0)
        path.write_text(op.page_content, encoding="utf-8")
        return ApplyResult(success=True, conflict=False, applied_lines=op.page_content.count("\n") + 1)
