# -*- coding: utf-8 -*-
"""Web 对比接口单元测试"""

import json
from pathlib import Path

import pytest

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
    snap_dir  = tmp_path / ".daily_reporter" / "snapshots"
    snap_dir.mkdir(parents=True)
    out_dir   = tmp_path / "reports"
    out_dir.mkdir()
    watch_dir = tmp_path / "watched"
    watch_dir.mkdir()

    config = {
        "watch_paths":   [str(watch_dir)],
        "snapshot_root": str(tmp_path / ".daily_reporter"),
        "output_root":   str(out_dir),
        "ai_provider":   "disabled",
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return {"tmp_path": tmp_path, "snap_dir": snap_dir,
            "out_dir": out_dir, "config_path": config_path}


def _make_snapshot(dirs, snap_id, files_dict=None):
    snap_dir = dirs["snap_dir"]
    if files_dict is None:
        files_dict = {
            "src/main.py":  {"hash": snap_id[:6], "lines": ["line1", "line2"]},
            "README.md":    {"hash": snap_id[6:12], "lines": ["# Title"]},
        }
    snap = {
        "id": snap_id,
        "timestamp": f"2026-03-04T{snap_id[9:].replace('-', ':')}",
        "label": "test",
        "trigger": "test",
        "file_count": len(files_dict),
        "skipped_count": 0,
        "files": files_dict,
    }
    (snap_dir / f"snapshot-{snap_id}.json").write_text(json.dumps(snap), encoding="utf-8")
    idx_path = snap_dir.parent / "index.json"
    index = json.loads(idx_path.read_text()) if idx_path.exists() else []
    index.append({"id": snap_id, "timestamp": snap["timestamp"],
                   "label": "test", "trigger": "test", "file_count": len(files_dict)})
    idx_path.write_text(json.dumps(index), encoding="utf-8")


@pytest.fixture
def app_compare(tmp_dirs):
    # snap_a：src/main.py + README.md
    _make_snapshot(tmp_dirs, "20260304-100000", {
        "src/main.py": {"hash": "aaa", "lines": ["line1"]},
        "README.md":   {"hash": "bbb", "lines": ["# Title"]},
    })
    # snap_b：src/main.py 修改，new_file.py 新增，README.md 删除
    _make_snapshot(tmp_dirs, "20260304-120000", {
        "src/main.py": {"hash": "ccc", "lines": ["line1", "line2_new"]},
        "new_file.py": {"hash": "ddd", "lines": ["new"]},
    })
    app = create_app(tmp_dirs["config_path"])
    return app, tmp_dirs


# ---------------------------------------------------------------------------
# 测试：GET /api/compare/{a}/{b}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compare_basic(app_compare):
    app, _ = app_compare
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/compare/20260304-100000/20260304-120000")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["snap_a"]["id"] == "20260304-100000"
    assert body["snap_b"]["id"] == "20260304-120000"


@pytest.mark.asyncio
async def test_compare_summary_counts(app_compare):
    app, _ = app_compare
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/compare/20260304-100000/20260304-120000")
    summary = r.json()["summary"]
    # README.md 删除，new_file.py 新增，src/main.py 修改
    assert summary["created"]  == 1
    assert summary["modified"] == 1
    assert summary["deleted"]  == 1
    assert summary["total"]    == 3


@pytest.mark.asyncio
async def test_compare_diffs_structure(app_compare):
    app, _ = app_compare
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/compare/20260304-100000/20260304-120000")
    diffs = r.json()["diffs"]
    assert len(diffs) == 3
    paths = {d["path"] for d in diffs}
    assert "src/main.py" in paths
    assert "new_file.py" in paths
    assert "README.md" in paths
    statuses = {d["path"]: d["status"] for d in diffs}
    assert statuses["src/main.py"] == "modified"
    assert statuses["new_file.py"] == "created"
    assert statuses["README.md"]   == "deleted"


@pytest.mark.asyncio
async def test_compare_same_snapshot(app_compare):
    """起点与终点相同应返回 400。"""
    app, _ = app_compare
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/compare/20260304-100000/20260304-100000")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_compare_missing_snap_a(app_compare):
    app, _ = app_compare
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/compare/20260304-999999/20260304-120000")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_compare_missing_snap_b(app_compare):
    app, _ = app_compare
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/compare/20260304-100000/20260304-999999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_compare_invalid_id_format(app_compare):
    app, _ = app_compare
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/compare/INVALID/20260304-120000")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_compare_net_line_change(app_compare):
    """net 应为 total_add - total_remove。"""
    app, _ = app_compare
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/compare/20260304-100000/20260304-120000")
    summary = r.json()["summary"]
    assert summary["net"] == summary["total_add"] - summary["total_remove"]


# ---------------------------------------------------------------------------
# 测试：配置接口
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_config_api_key_masked(tmp_dirs):
    """ai_api_key 不能明文返回。"""
    config = json.loads(tmp_dirs["config_path"].read_text())
    config["ai_api_key"] = "super-secret-key"
    tmp_dirs["config_path"].write_text(json.dumps(config), encoding="utf-8")

    app = create_app(tmp_dirs["config_path"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/config")
    body = r.json()
    assert "super-secret-key" not in str(body)
    assert body["ai_api_key"] == "***"


@pytest.mark.asyncio
async def test_config_returns_ok(tmp_dirs):
    app = create_app(tmp_dirs["config_path"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["watch_paths"], list)
    assert body["ai_provider"] == "disabled"
