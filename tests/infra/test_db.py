import pytest

from sdd.infra.db import open_sdd_connection


def test_open_sdd_connection_rejects_duckdb_path():
    with pytest.raises(ValueError, match="I-NO-DUCKDB-1"):
        open_sdd_connection("/tmp/some_test.duckdb")


def test_open_sdd_connection_rejects_memory_path():
    with pytest.raises(ValueError, match="I-NO-DUCKDB-1"):
        open_sdd_connection(":memory:")


def test_open_sdd_connection_rejects_empty_path():
    with pytest.raises(ValueError, match="I-DB-1"):
        open_sdd_connection("")
