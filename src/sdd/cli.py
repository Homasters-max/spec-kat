"""SDD CLI router — pure Click adapter, no business logic (I-CLI-1)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from sdd.core.errors import SDDError


def _sdd_root() -> Path:
    env = os.environ.get("SDD_HOME")
    return Path(env).resolve() if env else Path(".sdd").resolve()


@click.group()
@click.version_option(package_name="sdd")
def cli() -> None:
    """SDD — Spec-Driven Development governance CLI."""
    from sdd.guards.norm import validate_registry_actions
    validate_registry_actions()


@cli.command("complete", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def complete(args: tuple[str, ...]) -> None:
    """Mark task T-NNN as DONE."""
    from sdd.commands.update_state import main
    sys.exit(main(["complete", *args]))


@cli.command("validate", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def validate(args: tuple[str, ...]) -> None:
    """Validate task T-NNN invariants."""
    from sdd.commands.update_state import main
    sys.exit(main(["validate", *args]))


@cli.command("show-state", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def show_state(args: tuple[str, ...]) -> None:
    """Print current State_index.yaml as a markdown table."""
    from sdd.commands.show_state import main
    sys.exit(main(list(args)))


@cli.command("path", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def path_cmd(args: tuple[str, ...]) -> None:
    """Resolve canonical SDD resource paths (§BOOTSTRAP STATE RULE)."""
    from sdd.commands.show_path import main
    sys.exit(main(list(args)))


@cli.command("activate-phase", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def activate_phase(args: tuple[str, ...]) -> None:
    """Transition a phase from PLANNED to ACTIVE."""
    from sdd.commands.activate_phase import main
    sys.exit(main(list(args)))


@cli.command("switch-phase", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def switch_phase(args: tuple[str, ...]) -> None:
    """Switch working context to a previously activated phase."""
    from sdd.commands.switch_phase import main
    sys.exit(main(list(args)))


@cli.command("replay", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def replay(args: tuple[str, ...]) -> None:
    """Replay L1 domain events from the EventLog."""
    from sdd.commands.query_events import main
    sys.exit(main(["--replay", *args]))


@cli.command("query-events", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def query_events(args: tuple[str, ...]) -> None:
    """Query the EventLog."""
    from sdd.commands.query_events import main
    sys.exit(main(list(args)))


@cli.command("metrics-report", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def metrics_report(args: tuple[str, ...]) -> None:
    """Generate a metrics report for a phase."""
    from sdd.commands.metrics_report import main
    sys.exit(main(list(args)))


@cli.command("sync-state", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def sync_state(args: tuple[str, ...]) -> None:
    """Rebuild State_index.yaml from EventLog replay."""
    from sdd.commands.update_state import main
    sys.exit(main(["sync", *args]))


@cli.command("bootstrap-complete", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def bootstrap_complete(args: tuple[str, ...]) -> None:
    """Bootstrap execution mode: complete a task without phase guard (I-BOOTSTRAP-1)."""
    from sdd.commands.bootstrap_complete import main
    sys.exit(main(list(args)))


@cli.command("reconcile-bootstrap", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def reconcile_bootstrap(args: tuple[str, ...]) -> None:
    """Backfill EventLog for bootstrap-completed tasks (stub until PhaseContextSwitch)."""
    from sdd.commands.reconcile_bootstrap import main
    sys.exit(main(list(args)))


@cli.command("validate-invariants")
@click.option("--phase", type=int, required=True, help="Phase number")
@click.option("--task", "task_id", default=None, help="Task ID (T-NNN)")
@click.option("--check", "check_id", default=None, help="Specific invariant check (I-XXX)")
@click.option("--scope", default=None, help="Scope for check (e.g. full-src)")
@click.option("--timeout", "timeout_secs", type=int, default=0, help="Subprocess timeout in seconds (0 = default 300)")
def validate_invariants(phase: int, task_id: str | None, check_id: str | None, scope: str | None, timeout_secs: int) -> None:
    """Run validation checks for a task and record results."""
    from sdd.commands.validate_invariants import main
    args: list[str] = ["--phase", str(phase)]
    if task_id:
        args += ["--task", task_id]
    if check_id:
        args += ["--check", check_id]
    if scope:
        args += ["--scope", scope]
    if timeout_secs:
        args += ["--timeout", str(timeout_secs)]
    sys.exit(main(args))


@cli.command("invalidate-event", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def invalidate_event(args: tuple[str, ...]) -> None:
    """Neutralize an invalid EventLog entry (BC-WG-5)."""
    from sdd.commands.invalidate_event import main
    sys.exit(main(list(args)))


@cli.command("report-error", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def report_error(args: tuple[str, ...]) -> None:
    """Report a structured SDD error to the EventLog."""
    from sdd.commands.report_error import main
    sys.exit(main(list(args)))


@cli.command("validate-config")
@click.option("--phase", type=int, required=True, help="Phase number to validate config for")
@click.option(
    "--config",
    "config_path",
    default=None,
    help="Path to project_profile.yaml (default: resolved via paths.py config_file())",
)
def validate_config(phase: int, config_path: str | None) -> None:
    """Validate project_profile.yaml and phases/phase_N.yaml structure."""
    from sdd.commands.validate_config import validate_project_config

    _root = _sdd_root()
    if config_path is None:
        config_path = str(_root / "config" / "project_profile.yaml")
    validate_project_config(phase, config_path)
    click.echo(f"Config valid for phase {phase}.")
    sys.exit(0)


@cli.command("phase-guard", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def phase_guard(args: tuple[str, ...]) -> None:
    """Check PhaseGuard preconditions (PG-1..PG-3)."""
    from sdd.guards.phase import main
    sys.exit(main(list(args)))


@cli.command("task-guard", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def task_guard(args: tuple[str, ...]) -> None:
    """Verify task Status == TODO before implementation."""
    from sdd.guards.task import main
    sys.exit(main(list(args)))


@cli.command("check-scope", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def check_scope(args: tuple[str, ...]) -> None:
    """Validate file access against SENAR scope norms."""
    from sdd.guards.scope import main
    sys.exit(main(list(args)))


@cli.command("norm-guard", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def norm_guard(args: tuple[str, ...]) -> None:
    """Check actor/action against SENAR norm catalog."""
    from sdd.guards.norm import main
    sys.exit(main(list(args)))


@cli.command("show-task", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def show_task_cmd(args: tuple[str, ...]) -> None:
    """Show task definition from TaskSet."""
    from sdd.commands.show_task import main
    sys.exit(main(list(args)))


@cli.command("show-spec", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def show_spec_cmd(args: tuple[str, ...]) -> None:
    """Show spec content for a phase."""
    from sdd.commands.show_spec import main
    sys.exit(main(list(args)))


@cli.command("show-plan")
@click.option("--phase", type=int, default=None, help="Phase number (auto-detected if omitted)")
def show_plan_cmd(phase: int | None) -> None:
    """Show plan content for a phase."""
    import yaml

    from sdd.commands.show_plan import show_plan

    if phase is None:
        try:
            data = yaml.safe_load((_sdd_root() / "runtime" / "State_index.yaml").read_text(encoding="utf-8"))
            phase = int(data["tasks"]["version"])
        except Exception as exc:
            json.dump({"error_type": "MissingState", "message": str(exc), "exit_code": 1}, sys.stderr)
            sys.stderr.write("\n")
            sys.exit(1)
    show_plan(phase)


@cli.command("record-decision")
@click.option("--decision-id", required=True, help="Decision identifier (D-NNN)")
@click.option("--title", required=True, help="Decision title")
@click.option("--summary", required=True, help="Decision summary (max 500 chars)")
@click.option("--phase", type=int, default=None, help="Phase number (defaults to current phase from EventLog replay)")
def record_decision(decision_id: str, title: str, summary: str, phase: int | None) -> None:
    """Record a design decision in the EventLog as DecisionRecordedEvent."""
    import uuid

    from sdd.commands.record_decision import RecordDecisionCommand
    from sdd.commands.registry import REGISTRY, execute_and_project, get_current_state

    _root = _sdd_root()
    _db = str(_root / "state" / "sdd_events.duckdb")

    if phase is None:
        state = get_current_state(_db)
        phase = state.phase_current

    command = RecordDecisionCommand(
        command_id=str(uuid.uuid4()),
        command_type="RecordDecision",
        payload={"decision_id": decision_id, "phase_id": phase},
        decision_id=decision_id,
        title=title,
        summary=summary,
        phase_id=phase,
    )
    execute_and_project(REGISTRY["record-decision"], command, db_path=_db)
    sys.exit(0)


@cli.command("record-session")
@click.option("--type", "session_type", required=True, help="Session type (IMPLEMENT, VALIDATE, PLAN, etc.)")
@click.option("--phase", type=int, default=None, help="Phase number (defaults to current phase from EventLog replay)")
@click.option("--task", "task_id", default=None, help="Task ID (T-NNN)")
@click.option("--plan-hash", "plan_hash", default="", help="Plan hash for session-plan binding (I-SESSION-PLAN-HASH-1)")
def record_session(session_type: str, phase: int | None, task_id: str | None, plan_hash: str) -> None:
    """Declare session type — emits SessionDeclaredEvent for audit trail (I-SESSION-DECLARED-1)."""
    import uuid

    from sdd.commands.record_session import RecordSessionCommand
    from sdd.commands.registry import REGISTRY, execute_and_project, get_current_state

    _root = _sdd_root()
    _db = str(_root / "state" / "sdd_events.duckdb")

    if phase is None:
        state = get_current_state(_db)
        phase = state.phase_current

    command = RecordSessionCommand(
        command_id=str(uuid.uuid4()),
        command_type="RecordSession",
        payload={"session_type": session_type, "task_id": task_id, "phase_id": phase, "plan_hash": plan_hash},
        session_type=session_type,
        task_id=task_id,
        phase_id=phase,
        plan_hash=plan_hash,
    )
    execute_and_project(REGISTRY["record-session"], command, db_path=_db)
    sys.exit(0)


@cli.command("approve-spec")
@click.option("--phase", type=int, required=True, help="Phase number")
def approve_spec_cmd(phase: int) -> None:
    """Approve a spec draft — records SpecApproved event (BC-31-1)."""
    import types
    import uuid

    from sdd.commands.registry import REGISTRY, execute_and_project

    _root = _sdd_root()
    _db = str(_root / "state" / "sdd_events.duckdb")

    command = types.SimpleNamespace(
        command_id=str(uuid.uuid4()),
        command_type="ApproveSpec",
        payload={"phase_id": phase},
        phase_id=phase,
        actor="human",
    )
    execute_and_project(REGISTRY["approve-spec"], command, db_path=_db)
    sys.exit(0)


@cli.command("amend-plan")
@click.option("--phase", type=int, required=True, help="Phase number")
@click.option("--reason", required=True, help="Reason for plan amendment")
def amend_plan_cmd(phase: int, reason: str) -> None:
    """Record plan amendment after post-activation edit (BC-31-2)."""
    import types
    import uuid

    from sdd.commands.registry import REGISTRY, execute_and_project

    _root = _sdd_root()
    _db = str(_root / "state" / "sdd_events.duckdb")

    command = types.SimpleNamespace(
        command_id=str(uuid.uuid4()),
        command_type="AmendPlan",
        payload={"phase_id": phase},
        phase_id=phase,
        reason=reason,
        actor="human",
    )
    execute_and_project(REGISTRY["amend-plan"], command, db_path=_db)
    sys.exit(0)


@cli.command("rebuild-state")
@click.option("--full", is_flag=True, default=False, help="Full rebuild from seq=0 (I-STATE-REBUILD-1)")
def rebuild_state_cmd(full: bool) -> None:
    """Rebuild full projection from seq=0 (I-STATE-REBUILD-1, I-1)."""
    import types
    import uuid

    from sdd.commands.registry import REGISTRY, execute_and_project

    _root = _sdd_root()
    _db = str(_root / "state" / "sdd_events.duckdb")

    command = types.SimpleNamespace(
        command_id=str(uuid.uuid4()),
        command_type="RebuildState",
        payload={"full": full},
    )
    execute_and_project(REGISTRY["rebuild-state"], command, db_path=_db)
    sys.exit(0)


def _emit_json_error(error_type: str, message: str, exit_code: int) -> None:
    json.dump({"error_type": error_type, "message": message, "exit_code": exit_code}, sys.stderr)
    sys.stderr.write("\n")


def main(args: list[str] | None = None) -> None:
    """Click entry point — five-path execution contract (BC-EXEC, I-FAIL-1)."""
    try:
        result = cli(standalone_mode=False, args=args)
        sys.exit(result or 0)                              # SUCCESS path
    except SDDError as e:
        _emit_json_error(type(e).__name__, str(e), 1)
        sys.exit(1)                                        # KNOWN_ERR path
    except click.ClickException as e:
        _emit_json_error("UsageError", e.format_message(), 1)
        sys.exit(1)                                        # USAGE_ERR path
    except Exception as e:                                 # noqa: BLE001
        _emit_json_error("UnexpectedException", str(e), 2)
        sys.exit(2)                                        # UNEXPECTED path
