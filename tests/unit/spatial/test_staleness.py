"""Tests for staleness.py — I-GIT-OPTIONAL, I-SI-5."""
from unittest.mock import MagicMock, patch

from sdd.spatial.index import SpatialIndex
from sdd.spatial.staleness import current_git_hash, is_stale, staleness_report


def _make_index(git_tree_hash: str | None) -> SpatialIndex:
    return SpatialIndex(nodes={}, built_at="2026-01-01T00:00:00Z", git_tree_hash=git_tree_hash)


class TestCurrentGitHash:
    def test_returns_blob_sha_from_ls_files(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="100644 abc123def456 0\tfile.py\n")
            result = current_git_hash("file.py", str(tmp_path))
        assert result == "abc123def456"

    def test_fallback_hash_object_for_untracked(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout="deadbeef1234\n"),
            ]
            result = current_git_hash("untracked.py", str(tmp_path))
        assert result == "deadbeef1234"

    def test_returns_none_when_git_unavailable(self, tmp_path):
        """I-GIT-OPTIONAL: git not found → None."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = current_git_hash("file.py", str(tmp_path))
        assert result is None

    def test_returns_none_when_subprocess_fails(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = current_git_hash("file.py", str(tmp_path))
        assert result is None


class TestIsStale:
    def test_stale_when_head_changed(self, tmp_path):
        """I-SI-5: index.git_tree_hash != current HEAD → stale=True."""
        index = _make_index("old_hash_abc")
        with patch("sdd.spatial.staleness._head_tree_hash", return_value="new_hash_xyz"):
            assert is_stale(index, str(tmp_path)) is True

    def test_not_stale_when_hash_matches(self, tmp_path):
        index = _make_index("same_hash_abc")
        with patch("sdd.spatial.staleness._head_tree_hash", return_value="same_hash_abc"):
            assert is_stale(index, str(tmp_path)) is False

    def test_not_stale_when_git_unavailable(self, tmp_path):
        """I-GIT-OPTIONAL: git недоступен → is_stale()=False."""
        index = _make_index("some_hash")
        with patch("sdd.spatial.staleness._head_tree_hash", return_value=None):
            assert is_stale(index, str(tmp_path)) is False

    def test_not_stale_when_index_has_no_git_hash(self, tmp_path):
        """I-GIT-OPTIONAL: index built without git → git_tree_hash=None → not stale."""
        index = _make_index(None)
        with patch("sdd.spatial.staleness._head_tree_hash", return_value="current_head"):
            assert is_stale(index, str(tmp_path)) is False


class TestStalenessReport:
    def test_report_when_stale(self, tmp_path):
        index = _make_index("old_hash")
        with patch("sdd.spatial.staleness._head_tree_hash", return_value="new_hash"):
            report = staleness_report(index, str(tmp_path))
        assert report["stale"] is True
        assert report["index_tree"] == "old_hash"
        assert report["head_tree"] == "new_hash"
        assert report["reason"] == "head_changed"

    def test_report_when_up_to_date(self, tmp_path):
        index = _make_index("same_hash")
        with patch("sdd.spatial.staleness._head_tree_hash", return_value="same_hash"):
            report = staleness_report(index, str(tmp_path))
        assert report["stale"] is False
        assert report["reason"] == "up_to_date"

    def test_report_when_git_unavailable(self, tmp_path):
        """I-GIT-OPTIONAL: git unavailable → stale=False, reason=git_unavailable."""
        index = _make_index("some_hash")
        with patch("sdd.spatial.staleness._head_tree_hash", return_value=None):
            report = staleness_report(index, str(tmp_path))
        assert report["stale"] is False
        assert report["head_tree"] is None
        assert report["reason"] == "git_unavailable"

    def test_report_when_index_built_without_git(self, tmp_path):
        """I-GIT-OPTIONAL: index.git_tree_hash=None → not stale."""
        index = _make_index(None)
        with patch("sdd.spatial.staleness._head_tree_hash", return_value="some_head"):
            report = staleness_report(index, str(tmp_path))
        assert report["stale"] is False
        assert report["index_tree"] is None
        assert report["reason"] == "index_built_without_git"
