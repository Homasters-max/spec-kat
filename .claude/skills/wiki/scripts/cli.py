from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)

_DEFAULT_VAULT = Path(os.environ.get("WIKI_VAULT", "/root/project/obsidian-vault"))


def _resolve_vault(vault: Path) -> Path:
    return vault.expanduser().resolve()


@app.command()
def ingest(
    file: Optional[Path] = typer.Argument(None, help="Raw file to ingest"),
    pending: bool = typer.Option(False, "--pending", help="List or process pending files"),
    take: Optional[int] = typer.Option(None, "--take", help="Process N pending files (requires --pending)"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT", help="Vault root"),
) -> None:
    """Ingest raw files into the wiki pipeline."""
    from git import GitRepo
    from ingest import cache_context_packet, make_context_packet
    from state import read_ingest_log

    vault_root = _resolve_vault(vault)

    if pending:
        repo = GitRepo(vault_root)
        files = repo.pending_raw_files()
        if not files:
            typer.echo("No pending files.")
            return

        if take is None:
            typer.echo(f"Pending ({len(files)}):")
            for f in files:
                typer.echo(f"  {f.relative_to(vault_root)}")
            return

        files = files[:take]
        known = {e.sha256 for e in read_ingest_log(vault_root)}

        for src in files:
            import hashlib
            digest = hashlib.sha256(src.read_bytes()).hexdigest()
            if digest in known:
                typer.echo(f"[SKIP] {src.relative_to(vault_root)}")
                continue
            _ingest_one(src, vault_root)
        return

    if file is None:
        typer.echo("Provide a file path or use --pending.", err=True)
        raise typer.Exit(1)

    src = file if file.is_absolute() else vault_root / file
    import hashlib
    from state import read_ingest_log as _ril
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    known = {e.sha256 for e in _ril(vault_root)}
    if digest in known:
        typer.echo(f"[SKIP] {src}")
        return
    _ingest_one(src, vault_root)


def _ingest_one(src: Path, vault_root: Path) -> None:
    from ingest import cache_context_packet, make_context_packet

    packet = make_context_packet(src, vault_root)
    cache_path = cache_context_packet(vault_root, packet)
    typer.echo(f"[OK] {src.name}")
    typer.echo(f"  sha256  : {packet.sha256}")
    typer.echo(f"  chunks  : {len(packet.content_chunks)}")
    typer.echo(f"  related : {[r.page_id for r in packet.related_pages[:5]]}")
    typer.echo(f"  hints   : {[h.term for h in packet.glossary_hints]}")
    typer.echo(f"  cache   : {cache_path}")


@app.command(name="validate-extraction")
def validate_extraction(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Validate runtime/tmp/extraction.json against ExtractionResult schema."""
    from apply import validate_extraction as _validate

    vault_root = _resolve_vault(vault)
    result = _validate(vault_root)
    typer.echo(
        f"[OK] extraction.json valid: "
        f"{len(result.entities)} entities, "
        f"{len(result.relations)} relations, "
        f"{len(result.conflicts)} conflicts, "
        f"{len(result.glossary_proposals)} proposals"
    )


@app.command(name="apply-drafts")
def apply_drafts(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Apply LLM draft files from runtime/tmp/ to wiki pages."""
    from apply import apply_drafts as _apply
    from repo import WikiRepo

    vault_root = _resolve_vault(vault)
    repo = WikiRepo(vault_root)
    results = _apply(vault_root, repo)
    total = len(results)
    ok = sum(1 for r in results if r.success)
    typer.echo(f"[DONE] {ok}/{total} drafts applied.")


@app.command()
def rebuild(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Rebuild derived/index.md and derived/graph.json from wiki pages."""
    from rebuild import rebuild_all

    rebuild_all(_resolve_vault(vault))


@app.command()
def lint(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Check wiki integrity: orphans, broken links, duplicates."""
    from lint import run_lint

    report = run_lint(_resolve_vault(vault))

    orphans = report["orphans"]
    broken = report["broken_links"]
    duplicates = report["duplicates"]

    if orphans:
        typer.echo(f"Orphans ({len(orphans)}):")
        for pid in orphans:
            typer.echo(f"  - {pid}")

    if broken:
        typer.echo(f"Broken links ({len(broken)}):")
        for item in broken:
            typer.echo(f"  - {item['src']} → [[{item['target']}]]")

    if duplicates:
        typer.echo(f"Duplicates ({len(duplicates)}):")
        for item in duplicates:
            typer.echo(f"  - {item['a']} ≈ {item['b']}")

    if not any([orphans, broken, duplicates]):
        typer.echo("[OK] No issues found.")
    else:
        raise typer.Exit(1)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(10, "--top-k"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Search wiki pages (BM25)."""
    from search import SearchEngine

    vault_root = _resolve_vault(vault)
    engine = SearchEngine(vault_root)
    results = engine.search(query, top_k=top_k)
    if not results:
        typer.echo("No results.")
        return
    for i, r in enumerate(results, 1):
        typer.echo(f"  {i:2}. [{r.score:.4f}] {r.page_id}")


@app.command()
def show(
    target: str = typer.Argument(..., help="Page id or page type (idea/pattern/tool)"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Show a wiki page by id, or list all pages of a given type."""
    from models import PageType
    from repo import WikiRepo

    vault_root = _resolve_vault(vault)
    repo = WikiRepo(vault_root)

    page_types = ("idea", "pattern", "tool")
    if target in page_types:
        pages = repo.list_pages(type=target)  # type: ignore[arg-type]
        if not pages:
            typer.echo(f"No pages of type '{target}'.")
            return
        typer.echo(f"{target} ({len(pages)}):")
        for pid in sorted(pages):
            typer.echo(f"  - {pid}")
    else:
        content = repo.load_page(target)
        if content is None:
            typer.echo(f"Page '{target}' not found.", err=True)
            raise typer.Exit(1)
        typer.echo(content)


@app.command()
def log(
    n: int = typer.Option(20, "--n", help="Number of entries to show"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Show last N log entries (ingest + query) sorted by timestamp desc."""
    from state import read_ingest_log, read_query_log

    vault_root = _resolve_vault(vault)

    ingest_entries = [
        {"ts": e.ts, "type": "ingest", "detail": e.file, "id": e.sha256[:8]}
        for e in read_ingest_log(vault_root)
    ]
    query_entries = [
        {"ts": e.ts, "type": "query", "detail": e.query, "id": e.query_id[:8]}
        for e in read_query_log(vault_root)
    ]

    all_entries = sorted(ingest_entries + query_entries, key=lambda x: x["ts"], reverse=True)
    shown = all_entries[:n]

    if not shown:
        typer.echo("No log entries.")
        return

    for entry in shown:
        typer.echo(f"  [{entry['ts']}] {entry['type']:6s}  {entry['id']}  {entry['detail']}")


@app.command()
def promote(
    query_id: str = typer.Argument(..., help="query_id from query_log"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Promote a query context snapshot to a cached ContextPacket."""
    from ingest import _dict_to_packet, cache_context_packet
    from state import read_query_log

    vault_root = _resolve_vault(vault)
    entries = read_query_log(vault_root)
    match = next((e for e in entries if e.query_id == query_id), None)
    if match is None:
        typer.echo(f"query_id '{query_id}' not found in query_log.", err=True)
        raise typer.Exit(1)

    if not match.context_snapshot:
        typer.echo("context_snapshot is empty for this query.", err=True)
        raise typer.Exit(1)

    packet = _dict_to_packet(match.context_snapshot)
    cache_path = cache_context_packet(vault_root, packet)
    typer.echo(f"[OK] Promoted query '{query_id}'")
    typer.echo(f"  sha256 : {packet.sha256}")
    typer.echo(f"  cache  : {cache_path}")


@app.command(name="sync-glossary")
def sync_glossary(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Interactive review of glossary_pending.yaml — accept proposals into glossary.yaml."""
    import yaml
    from config import load_glossary

    vault_root = _resolve_vault(vault)
    pending_path = vault_root / ".wiki" / "config" / "glossary_pending.yaml"

    if not pending_path.exists():
        typer.echo("No pending glossary proposals.")
        return

    proposals: list[dict] = yaml.safe_load(pending_path.read_text(encoding="utf-8")) or []
    if not proposals:
        typer.echo("glossary_pending.yaml is empty.")
        return

    glossary_path = vault_root / ".wiki" / "config" / "glossary.yaml"
    accepted: list[dict] = load_glossary(vault_root)
    skipped = 0
    added = 0

    typer.echo(f"Reviewing {len(proposals)} proposal(s). Commands: y=accept  n=skip  e=edit term\n")

    for prop in proposals:
        typer.echo(f"  term    : {prop.get('term')}")
        typer.echo(f"  page    : {prop.get('suggested_page')}")
        typer.echo(f"  type    : {prop.get('type')}")
        typer.echo(f"  reason  : {prop.get('reason')}")
        choice = typer.prompt("  → accept? [y/n/e]", default="n").strip().lower()

        if choice == "y":
            entry = {
                "term": prop["term"],
                "page": prop.get("suggested_page", ""),
                "aliases": prop.get("aliases", []),
                "type": prop.get("type", ""),
            }
            accepted.append(entry)
            added += 1
            typer.echo("  [ADDED]\n")
        elif choice == "e":
            new_term = typer.prompt("  new term", default=prop["term"])
            entry = {
                "term": new_term,
                "page": prop.get("suggested_page", ""),
                "aliases": prop.get("aliases", []),
                "type": prop.get("type", ""),
            }
            accepted.append(entry)
            added += 1
            typer.echo("  [ADDED (edited)]\n")
        else:
            skipped += 1
            typer.echo("  [SKIP]\n")

    glossary_path.write_text(yaml.dump(accepted, allow_unicode=True), encoding="utf-8")
    pending_path.write_text(yaml.dump([], allow_unicode=True), encoding="utf-8")
    typer.echo(f"[DONE] {added} added, {skipped} skipped. glossary_pending.yaml cleared.")


@app.command(name="curate-apply")
def curate_apply(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Apply curated drafts: read curate_plan.md, call apply-drafts, rebuild."""
    from apply import apply_drafts as _apply
    from rebuild import rebuild_all
    from repo import WikiRepo

    vault_root = _resolve_vault(vault)
    plan_path = vault_root / "runtime" / "tmp" / "curate_plan.md"

    if not plan_path.exists():
        typer.echo("runtime/tmp/curate_plan.md not found.", err=True)
        raise typer.Exit(1)

    plan_text = plan_path.read_text(encoding="utf-8")
    typer.echo("=== Curate Plan ===")
    typer.echo(plan_text)
    typer.echo("===================\n")

    repo = WikiRepo(vault_root)
    results = _apply(vault_root, repo)
    total = len(results)
    ok = sum(1 for r in results if r.success)
    typer.echo(f"[APPLY] {ok}/{total} drafts applied.")

    rebuild_all(vault_root)
    typer.echo("[REBUILD] derived/ updated.")


@app.command()
def evolve(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Launch the wiki-evolve skill in Claude Code."""
    typer.echo("Run /wiki skill in Claude Code and choose wiki-evolve")


if __name__ == "__main__":
    app()
