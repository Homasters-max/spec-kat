import os
from pathlib import Path

_sdd_root: Path | None = None


def get_sdd_root() -> Path:
    global _sdd_root
    if _sdd_root is None:
        env = os.environ.get("SDD_HOME")
        if env is not None:
            _sdd_root = Path(env).resolve()
        else:
            _sdd_root = Path(".sdd").resolve()
    return _sdd_root


def reset_sdd_root() -> None:
    global _sdd_root
    _sdd_root = None


def event_store_file() -> Path:
    return get_sdd_root() / "state" / "sdd_events.duckdb"


def event_store_url() -> str:
    """Single routing point for event store backend.

    I-DB-URL-REQUIRED-1: SDD_DATABASE_URL MUST be set.
    Raises EnvironmentError if not set (no DuckDB fallback).
    """
    pg_url = os.environ.get("SDD_DATABASE_URL")
    if not pg_url:
        raise EnvironmentError(
            "SDD_DATABASE_URL is not set. "
            "Run: source scripts/dev-up.sh"
        )
    return pg_url


def is_production_event_store(db_path: str) -> bool:
    """True if db_path refers to the production event store.

    I-PROD-GUARD-1: agreed with event_store_url().
    Raises EnvironmentError if SDD_DATABASE_URL is not set.
    """
    pg_url = os.environ.get("SDD_DATABASE_URL")
    if not pg_url:
        raise EnvironmentError(
            "SDD_DATABASE_URL is not set. "
            "Cannot determine production event store."
        )
    return db_path == pg_url


def state_file() -> Path:
    return get_sdd_root() / "runtime" / "State_index.yaml"


def audit_log_file() -> Path:
    return get_sdd_root() / "runtime" / "audit_log.jsonl"


def norm_catalog_file() -> Path:
    return get_sdd_root() / "norms" / "norm_catalog.yaml"


def config_file() -> Path:
    return get_sdd_root() / "config" / "project_profile.yaml"


def phases_index_file() -> Path:
    return get_sdd_root() / "plans" / "Phases_index.md"


def specs_dir() -> Path:
    return get_sdd_root() / "specs"


def specs_draft_dir() -> Path:
    return get_sdd_root() / "specs_draft"


def plans_dir() -> Path:
    return get_sdd_root() / "plans"


def tasks_dir() -> Path:
    return get_sdd_root() / "tasks"


def reports_dir() -> Path:
    return get_sdd_root() / "reports"


def templates_dir() -> Path:
    return get_sdd_root() / "templates"


def taskset_file(phase: int) -> Path:
    return get_sdd_root() / "tasks" / f"TaskSet_v{phase}.md"


def plan_file(phase: int) -> Path:
    return get_sdd_root() / "plans" / f"Plan_v{phase}.md"


def bootstrap_manifest_file() -> Path:
    return get_sdd_root() / "runtime" / "bootstrap_manifest.json"


def spatial_index_file() -> Path:
    return get_sdd_root() / "state" / "spatial_index.json"


def nav_session_file() -> Path:
    return get_sdd_root() / "state" / "nav_session.json"


def nav_session_lock_file() -> Path:
    return get_sdd_root() / "state" / "nav_session.lock"
