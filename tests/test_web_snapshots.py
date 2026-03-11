# -*- coding: utf-8 -*-
"""Web 快照接口单元测试"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

# httpx 是 FastAPI 测试标准客户端
try:
    from httpx import AsyncClient, ASGITransport
except ImportError:
    pytest.skip("httpx 未安装，请执行: pip install httpx", allow_module_level=True)

from daily_reporter.web.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dirs(tmp_path):
    """创建临时快照目录和配置文件。"""
    snap_dir    = tmp_path / ".daily_reporter" / "snapshots"
    snap_dir.mkdir(parents=True)
    out_dir     = tmp_path / "reports"
    out_dir.mkdir()
    watch_dir   = tmp_path / "watched"
    watch_dir.mkdir()

    config = {
        "watch_paths":   [str(watch_dir)],
        "snapshot_root": str(tmp_path / ".daily_reporter"),
        "output_root":   str(out_dir),
        "ai_provider":   "disabled",
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    return {
        "tmp_path":   tmp_path,
        "snap_dir":   snap_dir,
        "out_dir":    out_dir,
        "watch_dir":  watch_dir,
        "config_path": config_path,
    }


def _make_snapshot(snap_dir: Path, snap_id: str, label: str = "test", file_count: int = 3) -> None:
    """在 snap_dir 写入假快照文件 + index。"""
    snap = {
        "id": snap_id,
        "timestamp": f"2026-03-04T{snap_id[9:].replace('-', ':')}",
        "label": label,
        "trigger": "test",
        "file_count": file_count,
        "skipped_count": 0,
        "files": {
            "a/b.py":  {"hash": "abc123", "lines": ["line1", "line2"]},
            "c/d.txt": {"hash": "def456", "lines": ["hello"]},
            "e.md":    {"hash": "ghi789", "lines": None},
        },
    }
    snap_file = snap_dir / f"snapshot-{snap_id}.json"
    snap_file.write_text(json.dumps(snap), encoding="utf-8")

    # 更新 index
    idx_path = snap_dir.parent / "index.json"
    index = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else []
    index.append({
        "id":         snap_id,
        "timestamp":  snap["timestamp"],
        "label":      label,
        "trigger":    "test",
        "file_count": file_count,
    })
    idx_path.write_text(json.dumps(index), encoding="utf-8")


@pytest.fixture
def app_with_snaps(tmp_dirs):
    """预置两个快照的 FastAPI app。"""
    _make_snapshot(tmp_dirs["snap_dir"], "20260304-100000", "morning", 3)
    _make_snapshot(tmp_dirs["snap_dir"], "20260304-120000", "noon",    3)
    return create_app(tmp_dirs["config_path"]), tmp_dirs


# ---------------------------------------------------------------------------
# 测试：GET /api/snapshots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_snapshots_empty(tmp_dirs):
    app = create_app(tmp_dirs["config_path"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/snapshots")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_list_snapshots_with_data(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/snapshots")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    # 最新的排前面
    assert body["items"][0]["id"] == "20260304-120000"


@pytest.mark.asyncio
async def test_list_snapshots_pagination(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/snapshots?page=1&size=1")
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1


@pytest.mark.asyncio
async def test_list_snapshots_search(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/snapshots?q=morning")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["label"] == "morning"


# ---------------------------------------------------------------------------
# 测试：POST /api/snapshots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_snapshot(tmp_dirs):
    # watch_dir 有一个文件才能打快照
    (tmp_dirs["watch_dir"] / "hello.txt").write_text("hello", encoding="utf-8")
    app = create_app(tmp_dirs["config_path"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/snapshots", json={"label": "web-test"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["label"] == "web-test"
    assert body["file_count"] >= 1


# ---------------------------------------------------------------------------
# 测试：GET /api/snapshots/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_snapshot_detail(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/snapshots/20260304-100000")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "20260304-100000"
    assert body["files"]["total"] == 3
    assert len(body["files"]["items"]) == 3


@pytest.mark.asyncio
async def test_get_snapshot_not_found(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/snapshots/20260304-999999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_snapshot_invalid_id(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/snapshots/INVALID-ID")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_get_snapshot_file_search(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/snapshots/20260304-100000?q=.py")
    body = r.json()
    assert body["files"]["total"] == 1
    assert body["files"]["items"][0]["path"] == "a/b.py"


# ---------------------------------------------------------------------------
# 测试：DELETE /api/snapshots/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_snapshot(app_with_snaps):
    app, dirs = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete("/api/snapshots/20260304-100000")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # 再次查询应 404
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r2 = await c.get("/api/snapshots/20260304-100000")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_delete_snapshot_invalid_id(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete("/api/snapshots/bad__id")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 测试：DELETE /api/snapshots — 批量删除
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_delete_snapshots(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.request(
            "DELETE", "/api/snapshots",
            json={"ids": ["20260304-100000", "20260304-120000"]},
        )
    body = r.json()
    assert body["ok"] is True
    assert len(body["deleted"]) == 2
    assert body["failed"] == []


@pytest.mark.asyncio
async def test_bulk_delete_invalid_ids(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.request(
            "DELETE", "/api/snapshots",
            json={"ids": ["BAD-ID"]},
        )
    body = r.json()
    assert "BAD-ID" in body["failed"]
