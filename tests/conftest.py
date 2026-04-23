from __future__ import annotations

import tempfile
from collections.abc import Generator

import pytest

from sdd.infra.db import open_sdd_connection


@pytest.fixture()
def in_memory_db() -> Generator[object, None, None]:
    conn = open_sdd_connection(":memory:")
    yield conn
    conn.close()


@pytest.fixture()
def tmp_db_path(tmp_path: object) -> str:
    import pathlib

    return str(pathlib.Path(str(tmp_path)) / "test_sdd_events.duckdb")
