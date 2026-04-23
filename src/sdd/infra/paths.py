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
