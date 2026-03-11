# -*- coding: utf-8 -*-
"""Web Watch 路由单元测试"""

import json
from pathlib import Path

import pytest

try:
    from httpx import AsyncClient, ASGITransport
except ImportError:
    pytest.skip("httpx 未安装，请执行: pip install httpx", allow_module_level=True)

from daily_reporter.web.app import create_app
from daily_reporter.web.routes import watch as watch_module


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
        "auto_snapshot_times": ["09:00", "18:00"],
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return {"tmp_path": tmp_path, "watch_dir": watch_dir, "config_path": config_path}


@pytest.fixture
def app(tmp_dirs):
    return create_app(tmp_dirs["config_path"])


@pytest.fixture(autouse=True)
def _cleanup_watch():
    """确保每个测试后 watch 停止运行。"""
    yield
    watch_module._watch_running = False
    watch_module._stop_event.set()
    if watch_module._watch_thread and watch_module._watch_thread.is_alive():
        watch_module._watch_thread.join(timeout=3)
    watch_module._watch_thread = None
    with watch_module._watch_log_lock:
        watch_module._watch_log.clear()


# ---------------------------------------------------------------------------
# GET /api/watch/status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_watch_status_initial(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/watch/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["running"] is False
    assert isinstance(body["auto_snapshot_times"], list)
    assert isinstance(body["recent_log"], list)


# ---------------------------------------------------------------------------
# POST /api/watch/start & stop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_watch_start(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/watch/start")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "启动" in body["message"]


@pytest.mark.asyncio
async def test_watch_start_idempotent(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/watch/start")
        r = await c.post("/api/watch/start")
    assert r.status_code == 200
    assert "已在运行" in r.json()["message"]


@pytest.mark.asyncio
async def test_watch_stop_when_not_running(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/watch/stop")
    assert r.status_code == 200
    assert "未在运行" in r.json()["message"]


@pytest.mark.asyncio
async def test_watch_start_then_stop(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/watch/start")
        r = await c.post("/api/watch/stop")
    assert r.status_code == 200
    assert "停止" in r.json()["message"]


@pytest.mark.asyncio
async def test_watch_status_running_after_start(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/watch/start")
        r = await c.get("/api/watch/status")
    body = r.json()
    assert body["running"] is True


# ---------------------------------------------------------------------------
# _push_log internal
# ---------------------------------------------------------------------------

class TestPushLog:
    def test_push_log_adds_entry(self):
        watch_module._push_log("log", {"message": "test"})
        with watch_module._watch_log_lock:
            assert len(watch_module._watch_log) >= 1
            assert watch_module._watch_log[-1]["event"] == "log"

    def test_push_log_max_limit(self):
        for i in range(watch_module._MAX_LOG + 50):
            watch_module._push_log("log", {"message": f"msg-{i}"})
        with watch_module._watch_log_lock:
            assert len(watch_module._watch_log) <= watch_module._MAX_LOG


# ---------------------------------------------------------------------------
# _time_to_label
# ---------------------------------------------------------------------------

class TestTimeToLabel:
    def test_delegates_to_hm_to_label(self):
        assert watch_module._time_to_label("08:00") == "morning"
        assert watch_module._time_to_label("12:00") == "noon"
        assert watch_module._time_to_label("15:00") == "afternoon"
        assert watch_module._time_to_label("20:00") == "evening"
