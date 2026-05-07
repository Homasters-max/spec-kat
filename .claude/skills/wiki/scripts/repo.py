from __future__ import annotations

import hashlib
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import yaml

from models import ApplyResult, PageMeta, PageType, RewriteOp, WikiDiff

_PAGE_TYPES: tuple[PageType, ...] = ("idea", "pattern", "tool")


class WikiRepo:
    def __init__(self, vault_root: Path) -> None:
        self.vault_root = vault_root

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[dict, str]:
        """Return (frontmatter_dict, body) splitting YAML --- blocks."""
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                fm_text = text[3:end].strip()
                body = text[end + 4:].lstrip("\n")
                return yaml.safe_load(fm_text) or {}, body
        return {}, text

    def _prepend_frontmatter(
        self,
        page_id: str,
        page_type: str,
        meta: PageMeta,
        version: int = 1,
        created: str | None = None,
        updated: str | None = None,
    ) -> str:
        today = date.today().isoformat()
        fm = {
            "id": f"{page_type}/{page_id}",
            "page_type": page_type,
            "domain": meta.domain,
            "layer": meta.layer,
            "tags": meta.tags,
            "version": version,
            "created": created or today,
            "updated": updated or today,
            "sources": meta.sources,
        }
        return f"---\n{yaml.dump(fm, allow_unicode=True, sort_keys=False)}---\n"

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

    def create_page(self, page_id: str, page_type: PageType, content: str, meta: PageMeta | None = None) -> ApplyResult:
        if "." in page_id:
            raise ValueError(f"page_id must not contain dots: {page_id!r}")
        if self._find_page_path(page_id) is not None:
            raise ValueError(f"page already exists: {page_id!r}")
        path = self._page_path(page_id, page_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        if meta is not None:
            full_content = self._prepend_frontmatter(page_id, page_type, meta, version=1) + content
        else:
            full_content = content
        path.write_text(full_content, encoding="utf-8")
        return ApplyResult(success=True, conflict=False, applied_lines=full_content.count("\n") + 1)

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

            patched_text = path.read_text(encoding="utf-8")
            fm, body = self._parse_frontmatter(patched_text)
            if fm:
                fm["version"] = fm.get("version", 0) + 1
                fm["updated"] = date.today().isoformat()
                path.write_text(
                    f"---\n{yaml.dump(fm, allow_unicode=True, sort_keys=False)}---\n{body}",
                    encoding="utf-8",
                )

            applied = sum(1 for ln in diff.unified_diff.splitlines() if ln.startswith(("+", "-")) and not ln.startswith(("---", "+++")))
            return ApplyResult(success=True, conflict=False, applied_lines=applied)
        finally:
            patch_file.unlink(missing_ok=True)

    def rewrite_page(self, op: RewriteOp, meta: PageMeta | None = None) -> ApplyResult:
        path = self._find_page_path(op.page_id)
        if path is None:
            return ApplyResult(success=False, conflict=True, applied_lines=0)
        if meta is not None:
            existing = path.read_text(encoding="utf-8")
            old_fm, _ = self._parse_frontmatter(existing)
            old_version = old_fm.get("version", 0)
            old_created = old_fm.get("created")
            page_type = old_fm.get("page_type", "idea")
            full_content = self._prepend_frontmatter(
                op.page_id, page_type, meta,
                version=old_version + 1,
                created=old_created,
            ) + op.page_content
        else:
            full_content = op.page_content
        path.write_text(full_content, encoding="utf-8")
        return ApplyResult(success=True, conflict=False, applied_lines=full_content.count("\n") + 1)
