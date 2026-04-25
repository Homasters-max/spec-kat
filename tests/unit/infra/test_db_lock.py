from unittest.mock import patch

import duckdb
import pytest

from sdd.infra.db import DuckDBLockTimeoutError, open_sdd_connection


def test_open_sdd_connection_raises_lock_timeout_error(tmp_path):
    """Lock exhaustion must raise DuckDBLockTimeoutError, not raw IOException (I-LOCK-1)."""
    db_path = str(tmp_path / "test.db")
    lock_error = duckdb.IOException("Could not set lock on file")
    with patch("sdd.infra.db.duckdb.connect", side_effect=lock_error):
        with pytest.raises(DuckDBLockTimeoutError):
            open_sdd_connection(db_path=db_path, timeout_secs=0.1)


def test_open_sdd_connection_raises_io_error_immediately(tmp_path):
    """Non-lock IOException must propagate immediately without retry (I-LOCK-1)."""
    db_path = str(tmp_path / "test.db")
    io_error = duckdb.IOException("Disk full")
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise io_error

    with patch("sdd.infra.db.duckdb.connect", side_effect=side_effect):
        with pytest.raises(duckdb.IOException):
            open_sdd_connection(db_path=db_path, timeout_secs=5.0)
    assert call_count == 1


def test_open_sdd_connection_memory_no_retry():
    """For :memory: db, connection must be immediate with no retry loop (I-LOCK-2)."""
    with patch("sdd.infra.db.time.sleep") as mock_sleep:
        conn = open_sdd_connection(db_path=":memory:", timeout_secs=10.0)
        conn.close()
        mock_sleep.assert_not_called()
