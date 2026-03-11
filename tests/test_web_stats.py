# -*- coding: utf-8 -*-
"""Web Stats API 单元测试"""

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
    snap_dir = tmp_path / ".daily_reporter" / "snapshots"
    snap_dir.mkdir(parents=True)
    out_dir = tmp_path / "reports"
    out_dir.mkdir()
    watch_dir = tmp_path / "watched"
    watch_dir.mkdir()

    config = {
        "watch_paths": [str(watch_dir)],
        "snapshot_root": str(tmp_path / ".daily_reporter"),
        "output_root": str(out_dir),
        "ai_provider": "disabled",
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return {"tmp_path": tmp_path, "snap_dir": snap_dir,
            "out_dir": out_dir, "watch_dir": watch_dir, "config_path": config_path}


def _make_snapshot(dirs, snap_id, files_dict=None, label="test"):
    snap_dir = dirs["snap_dir"]
    if files_dict is None:
        files_dict = {
            "src/main.py": {"hash": snap_id[:6]},
        }
    content_dict = {}
    for path, meta in files_dict.items():
        if "lines" in meta:
            content_dict[path] = meta.pop("lines")

    snap_meta = {
        "id": snap_id,
        "timestamp": f"2026-03-04T{snap_id[9:11]}:{snap_id[11:13]}:{snap_id[13:15]}",
        "label": label,
        "trigger": "test",
        "file_count": len(files_dict),
        "skipped_count": 0,
        "files": files_dict,
    }
    (snap_dir / f"snapshot-{snap_id}.json").write_text(
        json.dumps(snap_meta), encoding="utf-8"
    )
    (snap_dir / f"snapshot-{snap_id}.content.json").write_text(
        json.dumps(content_dict), encoding="utf-8"
    )

    idx_path = snap_dir.parent / "index.json"
    index = json.loads(idx_path.read_text()) if idx_path.exists() else []
    index.append({
        "id": snap_id,
        "timestamp": snap_meta["timestamp"],
        "label": label,
        "trigger": "test",
        "file_count": len(files_dict),
    })
    idx_path.write_text(json.dumps(index), encoding="utf-8")


@pytest.fixture
def app_with_snaps(tmp_dirs):
    _make_snapshot(tmp_dirs, "20260304-100000", {
        "src/main.py": {"hash": "aaa", "lines": ["line1"]},
    }, label="morning")
    _make_snapshot(tmp_dirs, "20260304-120000", {
        "src/main.py": {"hash": "bbb", "lines": ["line1", "line2_new"]},
        "new_file.py": {"hash": "ccc", "lines": ["hello"]},
    }, label="noon")
    app = create_app(tmp_dirs["config_path"])
    return app, tmp_dirs


# ---------------------------------------------------------------------------
# GET /api/stats/activity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_activity_empty(tmp_dirs):
    app = create_app(tmp_dirs["config_path"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/stats/activity")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["heatmap"] == []
    assert body["trend"] == []
    assert len(body["hourly"]) == 24


@pytest.mark.asyncio
async def test_activity_heatmap_has_data(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/stats/activity")
    body = r.json()
    assert len(body["heatmap"]) >= 1
    entry = body["heatmap"][0]
    assert "date" in entry
    assert "count" in entry
    assert entry["count"] >= 1


@pytest.mark.asyncio
async def test_activity_trend_has_data(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/stats/activity")
    body = r.json()
    assert len(body["trend"]) >= 1
    entry = body["trend"][0]
    assert "date" in entry
    assert "added" in entry
    assert "removed" in entry
    assert "net" in entry


@pytest.mark.asyncio
async def test_activity_trend_line_counts(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/stats/activity")
    body = r.json()
    # snap_a -> snap_b: new_file.py created (1 line), main.py modified (1 added)
    total_add = sum(t["added"] for t in body["trend"])
    assert total_add > 0


@pytest.mark.asyncio
async def test_activity_hourly_24_entries(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/stats/activity")
    body = r.json()
    assert len(body["hourly"]) == 24
    hours = [h["hour"] for h in body["hourly"]]
    assert hours == list(range(24))


@pytest.mark.asyncio
async def test_activity_hourly_has_counts(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/stats/activity")
    body = r.json()
    # snapshots at 10:00 and 12:00
    hour10 = next(h for h in body["hourly"] if h["hour"] == 10)
    hour12 = next(h for h in body["hourly"] if h["hour"] == 12)
    assert hour10["count"] >= 1
    assert hour12["count"] >= 1


@pytest.mark.asyncio
async def test_activity_custom_days(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/stats/activity?days=7")
    body = r.json()
    assert body["ok"] is True
    assert body["days"] == 7


@pytest.mark.asyncio
async def test_activity_days_validation(app_with_snaps):
    app, _ = app_with_snaps
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/stats/activity?days=2")
    assert r.status_code == 422  # days < 7 should fail validation
