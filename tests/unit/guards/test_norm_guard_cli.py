"""Unit tests for sdd.guards.norm CLI (main())."""
from __future__ import annotations

import json

import pytest


_CATALOG_YAML = """\
norms:
  - norm_id: "NORM-TEST-001"
    actor: "llm"
    forbidden_actions:
      - "forbidden-action"
  - norm_id: "NORM-TEST-002"
    actor: "human"
    allowed_actions:
      - "human-action"
"""


@pytest.fixture
def catalog_file(tmp_path):
    f = tmp_path / "catalog.yaml"
    f.write_text(_CATALOG_YAML)
    return str(f)


# ── CLI: no args / help ───────────────────────────────────────────────────────


def test_main_no_args(capsys):
    from sdd.guards.norm import main
    rc = main([])
    assert rc == 0
    assert "Usage" in capsys.readouterr().out


def test_main_help(capsys):
    from sdd.guards.norm import main
    rc = main(["--help"])
    assert rc == 0


# ── CLI: bad subcommand ───────────────────────────────────────────────────────


def test_main_unknown_subcommand(capsys):
    from sdd.guards.norm import main
    rc = main(["badcmd"])
    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert "Unknown subcommand" in data["error"]


# ── CLI: missing required args ────────────────────────────────────────────────


def test_main_check_missing_actor_and_action(capsys):
    from sdd.guards.norm import main
    rc = main(["check"])
    assert rc == 1


def test_main_check_missing_action(capsys):
    from sdd.guards.norm import main
    rc = main(["check", "--actor", "llm"])
    assert rc == 1


# ── CLI: check forbidden ──────────────────────────────────────────────────────


def test_main_check_forbidden(catalog_file, capsys):
    from sdd.guards.norm import main
    rc = main(["check", "--actor", "llm", "--action", "forbidden-action",
               "--catalog", catalog_file])
    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert data["allowed"] is False
    assert data["norm_id"] == "NORM-TEST-001"


# ── CLI: check allowed ────────────────────────────────────────────────────────


def test_main_check_allowed(catalog_file, capsys):
    from sdd.guards.norm import main
    rc = main(["check", "--actor", "human", "--action", "human-action",
               "--catalog", catalog_file])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["allowed"] is True
    assert data["norm_id"] is None


# ── CLI: strict mode denies unknown ──────────────────────────────────────────


def test_main_check_unknown_action_strict(catalog_file, capsys):
    from sdd.guards.norm import main
    rc = main(["check", "--actor", "llm", "--action", "unknown-action",
               "--catalog", catalog_file])
    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert data["allowed"] is False


# ── CLI: bad catalog path ─────────────────────────────────────────────────────


def test_main_bad_catalog(capsys):
    from sdd.guards.norm import main
    rc = main(["check", "--actor", "llm", "--action", "x",
               "--catalog", "/nonexistent/path/catalog.yaml"])
    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert "error" in data
