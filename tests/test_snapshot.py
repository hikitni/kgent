# -*- coding: utf-8 -*-
"""Unit tests for daily_reporter.snapshot"""

import json
import pytest
from pathlib import Path

from daily_reporter.config import AppConfig
from daily_reporter.snapshot import (
    _snap_id,
    _snap_filename,
    _snap_content_filename,
    should_ignore,
    take_snapshot,
    load_snapshot,
    load_snapshot_meta,
    load_index,
    save_index,
    delete_snapshot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    watch = tmp_path / "watch"
    watch.mkdir()
    return AppConfig(
        watch_paths=[watch],
        snapshot_root=tmp_path / ".daily_reporter",
        output_root=tmp_path / "reports",
        ignore_dirs={".git", "__pycache__"},
        ignore_suffixes={".pyc", ".log"},
        ignore_patterns=[r"\.idea\\"],
        max_file_size_kb=1,  # 1 KB threshold for tests
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestSnapId:
    def test_format(self):
        import datetime as dt
        ts = dt.datetime(2026, 3, 5, 9, 30, 0)
        assert _snap_id(ts) == "20260305-093000"

    def test_filename(self):
        assert _snap_filename("20260305-093000") == "snapshot-20260305-093000.json"


# ---------------------------------------------------------------------------
# should_ignore
# ---------------------------------------------------------------------------

class TestShouldIgnore:
    def test_ignore_by_dir(self, cfg: AppConfig):
        p = Path("d:/project/.git/config")
        assert should_ignore(p, cfg) is True

    def test_ignore_by_suffix(self, cfg: AppConfig):
        p = Path("d:/project/app/main.pyc")
        assert should_ignore(p, cfg) is True

    def test_ignore_by_pattern(self, cfg: AppConfig):
        # Pattern r'\.idea\\' targets .idea\ in path string
        p = Path(r"d:\project\.idea\workspace.xml")
        assert should_ignore(p, cfg) is True

    def test_not_ignored_normal_file(self, cfg: AppConfig):
        p = Path("d:/project/main.py")
        assert should_ignore(p, cfg) is False

    def test_ignore_log_suffix(self, cfg: AppConfig):
        p = Path("d:/project/debug.log")
        assert should_ignore(p, cfg) is True

    def test_ignore_pycache_dir(self, cfg: AppConfig):
        p = Path("d:/project/__pycache__/app.cpython-312.pyc")
        assert should_ignore(p, cfg) is True


# ---------------------------------------------------------------------------
# load_index / save_index
# ---------------------------------------------------------------------------

class TestIndexIO:
    def test_load_index_empty_when_no_file(self, cfg: AppConfig):
        assert load_index(cfg) == []

    def test_save_and_load_index(self, cfg: AppConfig):
        entries = [{"id": "20260305-093000", "label": "morning"}]
        save_index(cfg, entries)
        assert load_index(cfg) == entries

    def test_save_index_creates_parent(self, cfg: AppConfig):
        assert not cfg.snapshot_root.exists()
        save_index(cfg, [])
        assert cfg.snapshot_root.exists()

    def test_overwrite_index(self, cfg: AppConfig):
        save_index(cfg, [{"id": "A"}])
        save_index(cfg, [{"id": "B"}, {"id": "C"}])
        idx = load_index(cfg)
        assert len(idx) == 2
        assert idx[0]["id"] == "B"


# ---------------------------------------------------------------------------
# take_snapshot
# ---------------------------------------------------------------------------

class TestTakeSnapshot:
    def test_snapshot_metadata(self, cfg: AppConfig):
        snap = take_snapshot(cfg, label="morning", trigger="manual")
        assert snap["label"] == "morning"
        assert snap["trigger"] == "manual"
        assert "id" in snap
        assert "timestamp" in snap

    def test_snapshot_captures_files(self, cfg: AppConfig):
        watch = cfg.watch_paths[0]
        (watch / "hello.py").write_text("print('hi')", encoding="utf-8")
        snap = take_snapshot(cfg, label="test")
        assert snap["file_count"] == 1
        assert any("hello.py" in k for k in snap["files"])

    def test_snapshot_respects_ignore_suffix(self, cfg: AppConfig):
        watch = cfg.watch_paths[0]
        (watch / "debug.log").write_text("log data", encoding="utf-8")
        snap = take_snapshot(cfg)
        assert snap["file_count"] == 0

    def test_snapshot_respects_ignore_dir(self, cfg: AppConfig):
        watch = cfg.watch_paths[0]
        git = watch / ".git"
        git.mkdir()
        (git / "config").write_text("[core]", encoding="utf-8")
        snap = take_snapshot(cfg)
        assert snap["file_count"] == 0

    def test_snapshot_file_stored_on_disk(self, cfg: AppConfig):
        snap = take_snapshot(cfg, label="disk-test")
        snap_file = cfg.snapshot_root / "snapshots" / f"snapshot-{snap['id']}.json"
        assert snap_file.exists()
        loaded = json.loads(snap_file.read_text(encoding="utf-8"))
        assert loaded["id"] == snap["id"]

    def test_snapshot_updates_index(self, cfg: AppConfig):
        take_snapshot(cfg, label="first")
        take_snapshot(cfg, label="second")
        idx = load_index(cfg)
        assert len(idx) == 2

    def test_large_file_only_stores_hash(self, cfg: AppConfig):
        """Files exceeding max_file_size_kb should store hash, not lines."""
        watch = cfg.watch_paths[0]
        # cfg.max_file_size_kb = 1 KB; write ~2 KB
        content = "x" * 2048
        (watch / "big.txt").write_text(content, encoding="utf-8")
        snap = take_snapshot(cfg)
        key = str((watch / "big.txt").resolve())
        assert snap["files"][key]["lines"] is None
        assert len(snap["files"][key]["hash"]) == 32  # MD5 hex

    def test_small_file_stores_lines(self, cfg: AppConfig):
        watch = cfg.watch_paths[0]
        (watch / "small.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
        snap = take_snapshot(cfg)
        key = str((watch / "small.py").resolve())
        assert isinstance(snap["files"][key]["lines"], list)


# ---------------------------------------------------------------------------
# load_snapshot
# ---------------------------------------------------------------------------

class TestLoadSnapshot:
    def test_load_saved_snapshot(self, cfg: AppConfig):
        snap = take_snapshot(cfg, label="load-test")
        loaded = load_snapshot(cfg, snap["id"])
        assert loaded["id"] == snap["id"]
        assert loaded["label"] == "load-test"

    def test_load_nonexistent_raises(self, cfg: AppConfig):
        with pytest.raises(FileNotFoundError):
            load_snapshot(cfg, "99991231-999999")


# ---------------------------------------------------------------------------
# delete_snapshot
# ---------------------------------------------------------------------------

class TestDeleteSnapshot:
    def test_delete_removes_file(self, cfg: AppConfig):
        snap = take_snapshot(cfg, label="to-delete")
        snap_file = cfg.snapshot_root / "snapshots" / f"snapshot-{snap['id']}.json"
        assert snap_file.exists()
        result = delete_snapshot(cfg, snap["id"])
        assert result is True
        assert not snap_file.exists()

    def test_delete_removes_from_index(self, cfg: AppConfig):
        snap = take_snapshot(cfg, label="del-idx")
        delete_snapshot(cfg, snap["id"])
        idx = load_index(cfg)
        assert all(e["id"] != snap["id"] for e in idx)

    def test_delete_nonexistent_returns_false(self, cfg: AppConfig):
        # Make sure index exists but entry is absent
        save_index(cfg, [])
        result = delete_snapshot(cfg, "00000000-000000")
        assert result is False

    def test_delete_keeps_other_entries(self, cfg: AppConfig):
        import json as _json
        # Set up two distinct snapshots with known IDs directly
        (cfg.snapshot_root / "snapshots").mkdir(parents=True, exist_ok=True)
        snap_a_id = "20260305-090000"
        snap_b_id = "20260305-180000"
        for sid in (snap_a_id, snap_b_id):
            f = cfg.snapshot_root / "snapshots" / f"snapshot-{sid}.json"
            f.write_text(_json.dumps({"id": sid, "files": {}}), encoding="utf-8")
        save_index(cfg, [
            {"id": snap_a_id, "label": "keep"},
            {"id": snap_b_id, "label": "remove"},
        ])
        delete_snapshot(cfg, snap_b_id)
        idx = load_index(cfg)
        assert len(idx) == 1
        assert idx[0]["id"] == snap_a_id


# ---------------------------------------------------------------------------
# _snap_content_filename
# ---------------------------------------------------------------------------

class TestSnapContentFilename:
    def test_format(self):
        assert _snap_content_filename("20260305-093000") == "snapshot-20260305-093000.content.json"


# ---------------------------------------------------------------------------
# Meta / Content 分离存储
# ---------------------------------------------------------------------------

class TestMetaContentSplit:
    def test_take_snapshot_creates_both_files(self, cfg: AppConfig):
        watch = cfg.watch_paths[0]
        (watch / "a.py").write_text("x = 1", encoding="utf-8")
        snap = take_snapshot(cfg)
        sdir = cfg.snapshot_root / "snapshots"
        assert (sdir / _snap_filename(snap["id"])).exists()
        assert (sdir / _snap_content_filename(snap["id"])).exists()

    def test_meta_file_has_no_lines(self, cfg: AppConfig):
        watch = cfg.watch_paths[0]
        (watch / "a.py").write_text("x = 1", encoding="utf-8")
        snap = take_snapshot(cfg)
        sdir = cfg.snapshot_root / "snapshots"
        meta = json.loads((sdir / _snap_filename(snap["id"])).read_text(encoding="utf-8"))
        for finfo in meta["files"].values():
            assert "lines" not in finfo  # meta only has hash

    def test_content_file_has_lines(self, cfg: AppConfig):
        watch = cfg.watch_paths[0]
        (watch / "a.py").write_text("line1\nline2", encoding="utf-8")
        snap = take_snapshot(cfg)
        sdir = cfg.snapshot_root / "snapshots"
        content = json.loads((sdir / _snap_content_filename(snap["id"])).read_text(encoding="utf-8"))
        found = False
        for lines in content.values():
            if isinstance(lines, list) and "line1" in lines:
                found = True
        assert found

    def test_load_snapshot_merges_meta_and_content(self, cfg: AppConfig):
        watch = cfg.watch_paths[0]
        (watch / "b.py").write_text("hello\nworld", encoding="utf-8")
        snap = take_snapshot(cfg)
        loaded = load_snapshot(cfg, snap["id"])
        found_lines = False
        for finfo in loaded["files"].values():
            if finfo.get("lines") is not None:
                found_lines = True
        assert found_lines

    def test_load_snapshot_backward_compat(self, cfg: AppConfig):
        """旧格式（单体 JSON）应依然可加载。"""
        sdir = cfg.snapshot_root / "snapshots"
        sdir.mkdir(parents=True, exist_ok=True)
        old_snap = {
            "id": "20260305-120000",
            "timestamp": "2026-03-05T12:00:00",
            "label": "old",
            "files": {
                "x.py": {"hash": "abc", "lines": ["a", "b"]},
            },
        }
        (sdir / "snapshot-20260305-120000.json").write_text(
            json.dumps(old_snap), encoding="utf-8"
        )
        loaded = load_snapshot(cfg, "20260305-120000")
        assert loaded["files"]["x.py"]["lines"] == ["a", "b"]


# ---------------------------------------------------------------------------
# load_snapshot_meta
# ---------------------------------------------------------------------------

class TestLoadSnapshotMeta:
    def test_returns_metadata(self, cfg: AppConfig):
        snap = take_snapshot(cfg, label="meta-test")
        meta = load_snapshot_meta(cfg, snap["id"])
        assert meta["id"] == snap["id"]
        assert meta["label"] == "meta-test"

    def test_meta_does_not_contain_lines(self, cfg: AppConfig):
        watch = cfg.watch_paths[0]
        (watch / "c.py").write_text("content", encoding="utf-8")
        snap = take_snapshot(cfg)
        meta = load_snapshot_meta(cfg, snap["id"])
        for finfo in meta.get("files", {}).values():
            assert "lines" not in finfo

    def test_meta_nonexistent_raises(self, cfg: AppConfig):
        with pytest.raises(FileNotFoundError):
            load_snapshot_meta(cfg, "99991231-999999")


# ---------------------------------------------------------------------------
# delete_snapshot — content file cleanup
# ---------------------------------------------------------------------------

class TestDeleteSnapshotContent:
    def test_delete_removes_content_file(self, cfg: AppConfig):
        watch = cfg.watch_paths[0]
        (watch / "d.py").write_text("content", encoding="utf-8")
        snap = take_snapshot(cfg)
        sdir = cfg.snapshot_root / "snapshots"
        content_file = sdir / _snap_content_filename(snap["id"])
        assert content_file.exists()
        delete_snapshot(cfg, snap["id"])
        assert not content_file.exists()
