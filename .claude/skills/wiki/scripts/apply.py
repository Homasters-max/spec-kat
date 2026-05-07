from __future__ import annotations

import json
import sys
from pathlib import Path

from models import ApplyResult, ExtractionResult, PageMeta, PageType, RewriteOp, WikiDiff
from repo import WikiRepo

_OPS = ("create", "diff", "rewrite")



def validate_extraction(vault_root: Path) -> ExtractionResult:
    """Read runtime/tmp/extraction.json and validate via pydantic (I-WIKI-EXTRACT-1)."""
    tmp_dir = vault_root / "runtime" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    extraction_path = tmp_dir / "extraction.json"
    if not extraction_path.exists():
        print(f"[ERROR] extraction.json not found: {extraction_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(extraction_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Invalid JSON in extraction.json: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        result = ExtractionResult.model_validate(data)
    except Exception as exc:
        print(f"[ERROR] ExtractionResult validation failed:\n{exc}", file=sys.stderr)
        sys.exit(1)

    return result


def apply_drafts(vault_root: Path, repo: WikiRepo, allowed_ids: set[str] | None = None) -> list[ApplyResult]:
    """Apply LLM draft files from runtime/tmp/ to wiki (I-WIKI-CONFLICT-1).

    allowed_ids: if given, only process drafts whose page_id is in this set (scoped apply).
    """
    tmp_dir = vault_root / "runtime" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    draft_files: list[tuple[str, str, Path]] = []
    for op in _OPS:
        for path in sorted(tmp_dir.glob(f"*.{op}.md")):
            page_id = path.name[: -(len(op) + 4)]  # strip .<op>.md
            draft_files.append((page_id, op, path))

    if allowed_ids is not None:
        draft_files = [(pid, op, path) for pid, op, path in draft_files if pid in allowed_ids]

    results: list[ApplyResult] = []

    for page_id, op, path in draft_files:
        text = path.read_text(encoding="utf-8")
        fm, body = WikiRepo._parse_frontmatter(text)

        if op == "create":
            page_type: PageType = fm.get("page_type", "idea")
            meta = PageMeta(
                tags=fm.get("tags", []),
                sources=fm.get("sources", []),
                domain=fm.get("domain", ""),
                layer=fm.get("layer", ""),
            )
            result = repo.create_page(page_id, page_type, body, meta=meta)

        elif op == "diff":
            base_sha256: str = fm.get("base_sha256", "")
            diff = WikiDiff(page_id=page_id, unified_diff=body, base_sha256=base_sha256)
            result = repo.apply_diff(diff)

        elif op == "rewrite":
            reason = fm.get("reason", "structural_change")
            meta = PageMeta(
                tags=fm.get("tags", []),
                sources=fm.get("sources", []),
                domain=fm.get("domain", ""),
                layer=fm.get("layer", ""),
            )
            rewrite_op = RewriteOp(page_id=page_id, page_content=body, reason=reason)
            result = repo.rewrite_page(rewrite_op, meta=meta)

        else:
            continue

        results.append(result)
        status = "OK" if result.success else "CONFLICT"
        print(f"[{status}] {op} {page_id} ({result.applied_lines} lines)")

        if result.conflict:
            print(f"[ERROR] Conflict on {page_id} — stopping (I-WIKI-CONFLICT-1)", file=sys.stderr)
            sys.exit(1)

    # Clean up tmp dir after all successful operations
    for _, _, path in draft_files:
        path.unlink(missing_ok=True)

    return results
