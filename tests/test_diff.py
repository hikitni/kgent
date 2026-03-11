# -*- coding: utf-8 -*-
"""Unit tests for daily_reporter.diff"""

import pytest
from daily_reporter.diff import (
    diff_snapshots,
    summarize_diff,
    _unified_diff_lines,
    _MAX_DIFF_LINES,
)


# ---------------------------------------------------------------------------
# Snapshot builder helpers
# ---------------------------------------------------------------------------

def _make_snap(files: dict, snap_id: str = "A") -> dict:
    """Create a minimal snapshot dict.

    files: {path_str: {"hash": "...", "lines": [...] | None}}
    """
    return {
        "id": snap_id,
        "timestamp": "2026-03-05T09:00:00",
        "label": "test",
        "files": files,
    }


def _file(lines: list, h: str | None = None) -> dict:
    import hashlib
    content = "\n".join(lines)
    digest = h or hashlib.md5(content.encode()).hexdigest()
    return {"hash": digest, "lines": lines}


def _large_file(h: str = "aabbccdd") -> dict:
    """Simulate a large file (lines=None, only hash)."""
    return {"hash": h, "lines": None}


# ---------------------------------------------------------------------------
# _unified_diff_lines
# ---------------------------------------------------------------------------

class TestUnifiedDiffLines:
    def test_added_line_marked(self):
        a = ["hello"]
        b = ["hello", "world"]
        result = _unified_diff_lines(a, b)
        assert any(l.startswith("+") for l in result)

    def test_removed_line_marked(self):
        a = ["hello", "world"]
        b = ["hello"]
        result = _unified_diff_lines(a, b)
        assert any(l.startswith("-") for l in result)

    def test_no_headers(self):
        a = ["line1", "line2"]
        b = ["line1", "changed"]
        result = _unified_diff_lines(a, b)
        for l in result:
            assert not l.startswith("---")
            assert not l.startswith("+++")
            assert not l.startswith("@@")

    def test_max_diff_lines_respected(self):
        a = [f"line_{i}" for i in range(200)]
        b = [f"changed_{i}" for i in range(200)]
        result = _unified_diff_lines(a, b)
        assert len(result) <= _MAX_DIFF_LINES

    def test_identical_returns_empty(self):
        a = ["same", "content"]
        b = ["same", "content"]
        result = _unified_diff_lines(a, b)
        # No diff lines expected (possibly context lines only, filtered to none)
        assert all(l.startswith(" ") for l in result) or result == []


# ---------------------------------------------------------------------------
# diff_snapshots
# ---------------------------------------------------------------------------

class TestDiffSnapshots:
    def test_created_file_detected(self):
        snap_a = _make_snap({})
        snap_b = _make_snap({"/new/file.py": _file(["x = 1"])})
        diffs = diff_snapshots(snap_a, snap_b)
        assert len(diffs) == 1
        assert diffs[0]["status"] == "created"
        assert diffs[0]["path"] == "/new/file.py"

    def test_deleted_file_detected(self):
        snap_a = _make_snap({"/old/file.py": _file(["a = 1"])})
        snap_b = _make_snap({})
        diffs = diff_snapshots(snap_a, snap_b)
        assert len(diffs) == 1
        assert diffs[0]["status"] == "deleted"

    def test_modified_file_detected(self):
        snap_a = _make_snap({"/app.py": _file(["a = 1"])})
        snap_b = _make_snap({"/app.py": _file(["a = 2"])})
        diffs = diff_snapshots(snap_a, snap_b)
        assert len(diffs) == 1
        assert diffs[0]["status"] == "modified"

    def test_unchanged_file_excluded(self):
        entry = _file(["same content"])
        snap_a = _make_snap({"/same.py": entry})
        snap_b = _make_snap({"/same.py": entry})
        diffs = diff_snapshots(snap_a, snap_b)
        assert diffs == []

    def test_multiple_statuses(self):
        entry_same = _file(["unchanged"])
        snap_a = _make_snap({
            "/same.py": entry_same,
            "/old.py":  _file(["will be deleted"]),
            "/mod.py":  _file(["version 1"]),
        })
        snap_b = _make_snap({
            "/same.py": entry_same,
            "/new.py":  _file(["newly created"]),
            "/mod.py":  _file(["version 2"]),
        })
        diffs = diff_snapshots(snap_a, snap_b)
        statuses = {d["path"]: d["status"] for d in diffs}
        assert statuses["/old.py"] == "deleted"
        assert statuses["/new.py"] == "created"
        assert statuses["/mod.py"] == "modified"
        assert "/same.py" not in statuses

    def test_added_lines_counted_for_created(self):
        snap_a = _make_snap({})
        snap_b = _make_snap({"/f.py": _file(["a", "b", "c"])})
        diffs = diff_snapshots(snap_a, snap_b)
        assert diffs[0]["added_lines"] == 3
        assert diffs[0]["removed_lines"] == 0

    def test_removed_lines_counted_for_deleted(self):
        snap_a = _make_snap({"/f.py": _file(["x", "y"])})
        snap_b = _make_snap({})
        diffs = diff_snapshots(snap_a, snap_b)
        assert diffs[0]["removed_lines"] == 2
        assert diffs[0]["added_lines"] == 0

    def test_net_lines_calculated(self):
        snap_a = _make_snap({"/f.py": _file(["a", "b"])})
        snap_b = _make_snap({"/f.py": _file(["a", "b", "c", "d"])})
        diffs = diff_snapshots(snap_a, snap_b)
        assert diffs[0]["net_lines"] == diffs[0]["added_lines"] - diffs[0]["removed_lines"]

    def test_ext_field_populated(self):
        snap_a = _make_snap({})
        snap_b = _make_snap({"/src/main.py": _file(["pass"])})
        diffs = diff_snapshots(snap_a, snap_b)
        assert diffs[0]["ext"] == ".py"

    def test_ext_field_no_suffix(self):
        snap_a = _make_snap({})
        snap_b = _make_snap({"/Makefile": _file(["build:"])})
        diffs = diff_snapshots(snap_a, snap_b)
        assert diffs[0]["ext"] == "[无后缀]"

    def test_large_file_flag(self):
        snap_a = _make_snap({"/big.bin": _large_file("hash1")})
        snap_b = _make_snap({"/big.bin": _large_file("hash2")})
        diffs = diff_snapshots(snap_a, snap_b)
        assert len(diffs) == 1
        assert diffs[0]["large_file"] is True
        assert diffs[0]["diff_content"] == []

    def test_created_diff_content_has_plus_lines(self):
        snap_a = _make_snap({})
        snap_b = _make_snap({"/new.py": _file(["alpha", "beta"])})
        diffs = diff_snapshots(snap_a, snap_b)
        content = diffs[0]["diff_content"]
        assert all(l.startswith("+") for l in content)

    def test_deleted_diff_content_has_minus_lines(self):
        snap_a = _make_snap({"/del.py": _file(["gamma"])})
        snap_b = _make_snap({})
        diffs = diff_snapshots(snap_a, snap_b)
        content = diffs[0]["diff_content"]
        assert all(l.startswith("-") for l in content)

    def test_results_sorted_by_path(self):
        snap_a = _make_snap({})
        snap_b = _make_snap({
            "/z.py": _file(["z"]),
            "/a.py": _file(["a"]),
            "/m.py": _file(["m"]),
        })
        diffs = diff_snapshots(snap_a, snap_b)
        paths = [d["path"] for d in diffs]
        assert paths == sorted(paths)

    def test_empty_snapshots_returns_empty(self):
        snap_a = _make_snap({})
        snap_b = _make_snap({})
        assert diff_snapshots(snap_a, snap_b) == []

    def test_counter_duplicate_lines_counted_correctly(self):
        """Counter 应精确统计重复行的增删数量。"""
        # a 有 3 行 "x"，b 有 5 行 "x" — added=2, removed=0
        snap_a = _make_snap({"/dup.py": _file(["x", "x", "x"])})
        snap_b = _make_snap({"/dup.py": _file(["x", "x", "x", "x", "x"])})
        diffs = diff_snapshots(snap_a, snap_b)
        assert len(diffs) == 1
        assert diffs[0]["added_lines"] == 2
        assert diffs[0]["removed_lines"] == 0

    def test_counter_mixed_duplicate_changes(self):
        """混合增删重复行。"""
        snap_a = _make_snap({"/m.py": _file(["a", "a", "b"])})
        snap_b = _make_snap({"/m.py": _file(["a", "b", "b"])})
        diffs = diff_snapshots(snap_a, snap_b)
        assert diffs[0]["added_lines"] == 1    # +1 "b"
        assert diffs[0]["removed_lines"] == 1  # -1 "a"


# ---------------------------------------------------------------------------
# summarize_diff
# ---------------------------------------------------------------------------

class TestSummarizeDiff:
    def _make_diff_list(self):
        snap_a = _make_snap({
            "/old.py": _file(["gone"]),
            "/mod.py": _file(["v1"]),
        })
        snap_b = _make_snap({
            "/new.py": _file(["created"]),
            "/mod.py": _file(["v2"]),
        })
        return diff_snapshots(snap_a, snap_b)

    def test_total_count(self):
        diffs = self._make_diff_list()
        s = summarize_diff(diffs)
        assert s["total"] == 3  # created, modified, deleted

    def test_created_list(self):
        diffs = self._make_diff_list()
        s = summarize_diff(diffs)
        assert len(s["created"]) == 1
        assert s["created"][0]["status"] == "created"

    def test_modified_list(self):
        diffs = self._make_diff_list()
        s = summarize_diff(diffs)
        assert len(s["modified"]) == 1

    def test_deleted_list(self):
        diffs = self._make_diff_list()
        s = summarize_diff(diffs)
        assert len(s["deleted"]) == 1

    def test_total_add_total_remove(self):
        snap_a = _make_snap({})
        snap_b = _make_snap({"/f.py": _file(["a", "b", "c"])})
        diffs = diff_snapshots(snap_a, snap_b)
        s = summarize_diff(diffs)
        assert s["total_add"] == 3
        assert s["total_remove"] == 0

    def test_net_lines(self):
        snap_a = _make_snap({"/f.py": _file(["x"])})
        snap_b = _make_snap({"/f.py": _file(["x", "y", "z"])})
        diffs = diff_snapshots(snap_a, snap_b)
        s = summarize_diff(diffs)
        assert s["net"] == s["total_add"] - s["total_remove"]

    def test_top_ext(self):
        snap_a = _make_snap({})
        snap_b = _make_snap({
            "/a.py": _file(["1"]),
            "/b.py": _file(["2"]),
            "/c.js": _file(["3"]),
        })
        diffs = diff_snapshots(snap_a, snap_b)
        s = summarize_diff(diffs)
        exts = [e for e, _ in s["top_ext"]]
        assert ".py" in exts

    def test_top_dir(self):
        snap_a = _make_snap({})
        snap_b = _make_snap({
            "/src/a.py": _file(["1"]),
            "/src/b.py": _file(["2"]),
            "/tests/c.py": _file(["3"]),
        })
        diffs = diff_snapshots(snap_a, snap_b)
        s = summarize_diff(diffs)
        dirs = [d for d, _ in s["top_dir"]]
        # Normalize to handle platform-specific path separators
        dirs_normalized = [d.replace("\\", "/") for d in dirs]
        assert "/src" in dirs_normalized

    def test_empty_diffs_all_zeros(self):
        s = summarize_diff([])
        assert s["total"] == 0
        assert s["total_add"] == 0
        assert s["total_remove"] == 0
        assert s["created"] == []
        assert s["modified"] == []
        assert s["deleted"] == []
