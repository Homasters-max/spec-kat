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


@app.command(name="mark-ingested")
def mark_ingested(
    sha256: str = typer.Argument(..., help="SHA256 of the ingested file"),
    file: str = typer.Option(..., "--file", help="Original file path (for log record)"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Record a file as ingested in ingest_log (run after full wiki-evolve cycle)."""
    import datetime
    from models import IngestLogEntry
    from state import append_ingest_log, read_ingest_log

    vault_root = _resolve_vault(vault)

    if not file:
        typer.echo("Error: --file is required.", err=True)
        raise typer.Exit(1)

    known = {e.sha256 for e in read_ingest_log(vault_root)}
    if sha256 in known:
        typer.echo(f"[SKIP] {sha256[:8]} already in ingest_log.")
        return

    cache_path = vault_root / "runtime" / "cache" / f"{sha256}.json"
    entry = IngestLogEntry(
        sha256=sha256,
        file=file,
        ts=datetime.datetime.utcnow().isoformat(),
        packet_path=str(cache_path),
    )
    append_ingest_log(vault_root, entry)
    typer.echo(f"[OK] Marked {sha256[:8]} as ingested.")


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
    """Check wiki integrity: orphans, broken links, duplicates, frontmatter."""
    from config import load_config
    from lint import run_lint

    vault_root = _resolve_vault(vault)

    # Load domains/layers from config if available (E1/E2); fallback = no validation
    domains: list[str] | None = None
    layers: list[str] | None = None
    try:
        cfg = load_config(vault_root)
        domains = getattr(cfg, "domains", None)
        layers = getattr(cfg, "layers", None)
    except Exception:
        pass

    report = run_lint(vault_root, domains=domains, layers=layers)

    orphans = report["orphans"]
    broken = report["broken_links"]
    duplicates = report["duplicates"]
    warnings = report["warnings"]
    errors = report["errors"]

    if warnings:
        for item in warnings:
            typer.echo(f"WARNING: {item['page_id']}: {item['message']}")

    if errors:
        for item in errors:
            typer.echo(f"ERROR: {item['page_id']}: {item['message']}")

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

    has_errors = any([errors, broken, duplicates])
    if not any([warnings, errors, orphans, broken, duplicates]):
        typer.echo("[OK] No issues found.")
    elif has_errors:
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


@app.command(name="log-query")
def log_query(
    query: str = typer.Option(..., "--query", help="The query text to record"),
    snapshot: Optional[Path] = typer.Option(None, "--snapshot", help="Path to JSON file with context_snapshot"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Record a query in query_log and print the generated query_id."""
    import datetime
    import json
    import uuid

    from models import QueryLogEntry
    from state import append_query_log

    vault_root = _resolve_vault(vault)

    context_snapshot: dict = {}
    if snapshot is not None:
        snap_path = snapshot if snapshot.is_absolute() else Path.cwd() / snapshot
        if not snap_path.exists():
            typer.echo(f"Snapshot file not found: {snap_path}", err=True)
            raise typer.Exit(1)
        try:
            context_snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            typer.echo(f"Invalid JSON in snapshot file: {exc}", err=True)
            raise typer.Exit(1)
        if not isinstance(context_snapshot, dict):
            typer.echo("Snapshot file must contain a JSON object (dict).", err=True)
            raise typer.Exit(1)

    query_id = uuid.uuid4().hex[:12]
    ts = datetime.datetime.utcnow().isoformat()
    entry = QueryLogEntry(query_id=query_id, query=query, ts=ts, context_snapshot=context_snapshot)
    append_query_log(vault_root, entry)
    typer.echo(query_id)


@app.command()
def status(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Show current wiki pipeline state: pending files, tmp drafts, logs."""
    from git import GitRepo
    from state import read_ingest_log, read_query_log

    vault_root = _resolve_vault(vault)

    try:
        repo = GitRepo(vault_root)
        pending = repo.pending_raw_files()
    except Exception:
        pending = []
    typer.echo(f"Pending raw files : {len(pending)}")
    for f in pending[:5]:
        typer.echo(f"  {f.relative_to(vault_root)}")
    if len(pending) > 5:
        typer.echo(f"  ... and {len(pending) - 5} more")

    tmp_dir = vault_root / "runtime" / "tmp"
    extraction = tmp_dir / "extraction.json"
    typer.echo(f"extraction.json   : {'EXISTS' if extraction.exists() else 'missing'}")
    drafts = (
        list(tmp_dir.glob("*.create.md"))
        + list(tmp_dir.glob("*.diff.md"))
        + list(tmp_dir.glob("*.rewrite.md"))
    )
    typer.echo(f"Draft files (tmp) : {len(drafts)}")
    for d in drafts[:5]:
        typer.echo(f"  {d.name}")

    ingest_entries = read_ingest_log(vault_root)
    query_entries = read_query_log(vault_root)
    typer.echo(f"Ingest log entries: {len(ingest_entries)}")
    typer.echo(f"Query log entries  : {len(query_entries)}")
    if ingest_entries:
        last = ingest_entries[-1]
        typer.echo(f"  Last ingest: {last.ts[:19]}  {last.file}")


@app.command(name="save-proposals")
def save_proposals(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Merge glossary_proposals from extraction.json into glossary_pending.yaml."""
    import json

    import yaml

    vault_root = _resolve_vault(vault)
    extraction_path = vault_root / "runtime" / "tmp" / "extraction.json"

    if not extraction_path.exists():
        typer.echo("runtime/tmp/extraction.json not found.", err=True)
        raise typer.Exit(1)

    data = json.loads(extraction_path.read_text(encoding="utf-8"))
    proposals = data.get("glossary_proposals", [])
    if not proposals:
        typer.echo("[OK] 0 added, 0 skipped (no proposals in extraction.json)")
        return

    pending_path = vault_root / ".wiki" / "config" / "glossary_pending.yaml"
    existing: list[dict] = []
    if pending_path.exists():
        existing = yaml.safe_load(pending_path.read_text(encoding="utf-8")) or []

    existing_terms = {e.get("term") for e in existing}
    added = 0
    skipped = 0

    for prop in proposals:
        term = prop.get("term")
        if term in existing_terms:
            typer.echo(f"[SKIP] {term} (already pending)", err=True)
            skipped += 1
        else:
            existing.append(prop)
            existing_terms.add(term)
            added += 1

    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(yaml.dump(existing, allow_unicode=True), encoding="utf-8")
    typer.echo(f"[OK] {added} added, {skipped} skipped")


@app.command(name="delete")
def delete_page(
    page_id: str = typer.Argument(..., help="Page id to delete"),
    confirm: bool = typer.Option(False, "--confirm", help="Execute deletion (default is dry-run)"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Delete a wiki page: remove file, incoming links, glossary entry, rebuild."""
    import re

    import yaml
    from config import load_glossary
    from rebuild import rebuild_all

    vault_root = _resolve_vault(vault)
    wiki_dir = vault_root / "wiki"

    # Locate the page file
    page_file: Path | None = None
    for pt in ("idea", "pattern", "tool"):
        candidate = wiki_dir / pt / f"{page_id}.md"
        if candidate.exists():
            page_file = candidate
            break

    if page_file is None:
        typer.echo(f"Page '{page_id}' not found.", err=True)
        raise typer.Exit(1)

    # Find pages that reference [[page_id]]
    link_pattern = re.compile(r"\[\[" + re.escape(page_id) + r"\]\]")
    referencing: list[Path] = []
    for md in wiki_dir.rglob("*.md"):
        if md == page_file:
            continue
        if link_pattern.search(md.read_text(encoding="utf-8")):
            referencing.append(md)

    # Check glossary
    glossary_path = vault_root / ".wiki" / "config" / "glossary.yaml"
    glossary: list[dict] = load_glossary(vault_root)
    glossary_entry = next((e for e in glossary if e.get("page") == page_id), None)

    if not confirm:
        # Dry-run: show info
        lines = page_file.read_text(encoding="utf-8").splitlines()
        typer.echo(f"=== {page_id} (first 10 lines) ===")
        for ln in lines[:10]:
            typer.echo(f"  {ln}")

        if referencing:
            typer.echo(f"\nReferenced by ({len(referencing)}):")
            for p in referencing:
                typer.echo(f"  - {p.relative_to(vault_root)}")
        else:
            typer.echo("\nNo incoming links.")

        if glossary_entry:
            typer.echo(f"\nGlossary entry: term='{glossary_entry.get('term')}' → will be removed")
        else:
            typer.echo("\nNo glossary entry.")

        typer.echo(f"\nRun with --confirm to proceed.")
        return

    # --confirm: execute deletion
    # 1. Update referencing pages
    see_also_pattern = re.compile(r"^-\s+\[\[" + re.escape(page_id) + r"\]\]\s*$", re.MULTILINE)
    updated_count = 0
    for p in referencing:
        text = p.read_text(encoding="utf-8")
        # Remove See Also list items
        text = see_also_pattern.sub("", text)
        # Replace inline [[page_id]] with plain page_id
        text = link_pattern.sub(page_id, text)
        p.write_text(text, encoding="utf-8")
        updated_count += 1

    # 2. Remove glossary entry
    glossary_removed = False
    if glossary_entry:
        glossary = [e for e in glossary if e.get("page") != page_id]
        glossary_path.write_text(yaml.dump(glossary, allow_unicode=True), encoding="utf-8")
        glossary_removed = True

    # 3. Delete page file
    page_file.unlink()

    # 4. Rebuild derived/
    rebuild_all(vault_root)

    glossary_status = "removed" if glossary_removed else "kept"
    typer.echo(f"Deleted {page_id}. Updated {updated_count} pages. Glossary: {glossary_status}.")


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


@app.command(name="init")
def init_vault(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
    domain: str = typer.Option("personal", "--domain", help="Wiki domain name"),
    model: str = typer.Option("claude-sonnet-4-6", "--model", help="LLM model"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing config"),
) -> None:
    """Initialise a new wiki vault: create directory structure and config files."""
    import subprocess

    import yaml

    vault_root = _resolve_vault(vault)

    dirs = [
        vault_root / "raw",
        vault_root / "wiki" / "idea",
        vault_root / "wiki" / "pattern",
        vault_root / "wiki" / "tool",
        vault_root / "derived",
        vault_root / "runtime" / "cache",
        vault_root / "runtime" / "tmp",
        vault_root / ".wiki" / "config",
        vault_root / ".wiki" / "state",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        typer.echo(f"  [dir]  {d.relative_to(vault_root)}")

    config_path = vault_root / ".wiki" / "config" / "wiki_config.yaml"
    if config_path.exists() and not force:
        typer.echo(f"\n[SKIP] {config_path} already exists (use --force to overwrite)")
    else:
        config = {
            "domain": domain,
            "llm_model": model,
            "small_page_threshold": 1000,
            "vault_root": str(vault_root),
        }
        config_path.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")
        typer.echo(f"\n  [cfg]  .wiki/config/wiki_config.yaml")

    glossary_path = vault_root / ".wiki" / "config" / "glossary.yaml"
    if not glossary_path.exists():
        glossary_path.write_text("[]\n", encoding="utf-8")
        typer.echo(f"  [cfg]  .wiki/config/glossary.yaml")

    for name in ("ingest_log.jsonl", "query_log.jsonl"):
        p = vault_root / ".wiki" / "state" / name
        if not p.exists():
            p.touch()
            typer.echo(f"  [log]  .wiki/state/{name}")

    git_dir = vault_root / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init", str(vault_root)], check=True, capture_output=True)
        typer.echo(f"  [git]  initialized repository")
    else:
        typer.echo(f"  [git]  already a git repo")

    typer.echo(f"\n[OK] Vault ready at {vault_root}")
    typer.echo(f"     Drop files into raw/ then run: wiki ingest --pending")


if __name__ == "__main__":
    app()
