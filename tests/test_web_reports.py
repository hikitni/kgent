# -*- coding: utf-8 -*-
"""Web 日报接口单元测试"""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

try:
    from httpx import AsyncClient, ASGITransport
except ImportError:
    pytest.skip("httpx 未安装，请执行: pip install httpx", allow_module_level=True)

from daily_reporter.web.app import create_app
from daily_reporter.web.routes import reports as reports_module


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


def _make_snapshot(dirs, snap_id, label="test"):
    snap_dir = dirs["snap_dir"]
    snap = {
        "id": snap_id,
        "timestamp": f"2026-03-04T{snap_id[9:].replace('-', ':')}",
        "label": label,
        "trigger": "test",
        "file_count": 2,
        "skipped_count": 0,
        "files": {
            "a.py": {"hash": "aaa", "lines": ["x"]},
            "b.md": {"hash": "bbb", "lines": ["y"]},
        },
    }
    (snap_dir / f"snapshot-{snap_id}.json").write_text(json.dumps(snap), encoding="utf-8")
    idx_path = snap_dir.parent / "index.json"
    index = json.loads(idx_path.read_text()) if idx_path.exists() else []
    index.append({"id": snap_id, "timestamp": snap["timestamp"],
                   "label": label, "trigger": "test", "file_count": 2})
    idx_path.write_text(json.dumps(index), encoding="utf-8")


def _make_report(dirs, name, content="# 日报\n\n内容"):
    path = dirs["out_dir"] / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def app_with_reports(tmp_dirs):
    _make_snapshot(tmp_dirs, "20260304-100000", "morning")
    _make_snapshot(tmp_dirs, "20260304-120000", "noon")
    _make_report(tmp_dirs, "report-20260304-100000-to-20260304-120000.md", "# 原始日报\n\n内容")
    _make_report(tmp_dirs, "report-20260304-100000-to-20260304-120000-ai.md", "# AI 日报\n\n内容")
    # 每次 fixture 清空异步任务池
    reports_module._ai_tasks.clear()
    app = create_app(tmp_dirs["config_path"])
    return app, tmp_dirs


# ---------------------------------------------------------------------------
# 测试：GET /api/reports
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_reports_empty(tmp_dirs):
    app = create_app(tmp_dirs["config_path"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/reports")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_list_reports_all(app_with_reports):
    app, _ = app_with_reports
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/reports")
    body = r.json()
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_list_reports_filter_ai(app_with_reports):
    app, _ = app_with_reports
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/reports?type=ai")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["is_ai"] is True


@pytest.mark.asyncio
async def test_list_reports_filter_raw(app_with_reports):
    app, _ = app_with_reports
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/reports?type=raw")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["is_ai"] is False


@pytest.mark.asyncio
async def test_list_reports_pagination(app_with_reports):
    app, _ = app_with_reports
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/reports?page=1&size=1")
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1


# ---------------------------------------------------------------------------
# 测试：GET /api/reports/{name}/content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_report_content(app_with_reports):
    app, _ = app_with_reports
    name = "report-20260304-100000-to-20260304-120000.md"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/reports/{name}/content")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "原始日报" in body["content"]


@pytest.mark.asyncio
async def test_get_report_content_not_found(app_with_reports):
    app, _ = app_with_reports
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/reports/report-nonexistent.md/content")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_report_content_invalid_name(app_with_reports):
    app, _ = app_with_reports
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # 文件名含非法字符（不符合 ^report-[\w-]+\.md$ 正则），路由层应返回 400
        r = await c.get("/api/reports/invalid..name.txt/content")
    assert r.status_code in (400, 404, 422)


# ---------------------------------------------------------------------------
# 测试：POST /api/reports/generate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_report(app_with_reports):
    app, _ = app_with_reports
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/reports/generate",
                         json={"snap_a": "20260304-100000", "snap_b": "20260304-120000"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "report-" in body["filename"]
    assert body["filename"].endswith(".md")


@pytest.mark.asyncio
async def test_generate_report_missing_snap(app_with_reports):
    app, _ = app_with_reports
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/reports/generate",
                         json={"snap_a": "20260304-999999", "snap_b": "20260304-120000"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 测试：POST /api/reports/{name}/ai
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_ai_disabled(app_with_reports):
    """ai_provider=disabled 时应返回 503。"""
    app, _ = app_with_reports
    name = "report-20260304-100000-to-20260304-120000.md"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(f"/api/reports/{name}/ai")
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_generate_ai_already_ai(app_with_reports):
    """对 AI 日报再次请求 AI 应返回 400。"""
    app, _ = app_with_reports
    name = "report-20260304-100000-to-20260304-120000-ai.md"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(f"/api/reports/{name}/ai")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 测试：DELETE /api/reports/{name}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_report(app_with_reports):
    app, dirs = app_with_reports
    name = "report-20260304-100000-to-20260304-120000.md"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete(f"/api/reports/{name}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # 文件已被删除
    assert not (dirs["out_dir"] / name).exists()


@pytest.mark.asyncio
async def test_delete_report_not_found(app_with_reports):
    app, _ = app_with_reports
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete("/api/reports/report-ghost.md")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 测试：GET /api/reports/ai-tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_tasks_empty(app_with_reports):
    """初始状态无 AI 任务。"""
    app, _ = app_with_reports
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/reports/ai-tasks")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["tasks"] == []


# ---------------------------------------------------------------------------
# 测试：POST /api/reports/{name}/ai — 异步任务
# ---------------------------------------------------------------------------

@pytest.fixture
def app_ai_enabled(tmp_dirs):
    """配置 ai_provider=openai（非 disabled），用于测试异步 AI 提交。"""
    config_path = tmp_dirs["config_path"]
    cfg = json.loads(config_path.read_text())
    cfg["ai_provider"] = "openai"
    cfg["ai_api_key"] = "test-key"
    cfg["ai_model"] = "gpt-4o"
    config_path.write_text(json.dumps(cfg), encoding="utf-8")

    _make_snapshot(tmp_dirs, "20260304-100000", "morning")
    _make_snapshot(tmp_dirs, "20260304-120000", "noon")
    _make_report(tmp_dirs, "report-20260304-100000-to-20260304-120000.md", "# 原始日报\n\n测试内容")
    reports_module._ai_tasks.clear()
    app = create_app(config_path)
    return app, tmp_dirs


@pytest.mark.asyncio
async def test_ai_submit_returns_202(app_ai_enabled):
    """提交 AI 生成任务应立即返回 202。"""
    app, _ = app_ai_enabled
    name = "report-20260304-100000-to-20260304-120000.md"

    # mock AI 生成，避免实际调用外部 API
    with patch("daily_reporter.ai.generate_full_report", return_value="# AI 结果"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(f"/api/reports/{name}/ai")

    assert r.status_code == 202
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "running"
    assert body["task_id"] == name


@pytest.mark.asyncio
async def test_ai_duplicate_returns_409(app_ai_enabled):
    """重复提交同一日报 AI 生成应返回 409。"""
    app, _ = app_ai_enabled
    name = "report-20260304-100000-to-20260304-120000.md"

    # 手动注册一个 running 任务
    import time
    reports_module._ai_tasks[name] = {
        "status": "running", "filename": None, "error": None, "start_time": time.time()
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(f"/api/reports/{name}/ai")

    assert r.status_code == 409


@pytest.mark.asyncio
async def test_ai_task_completion(app_ai_enabled):
    """AI 任务完成后，ai-tasks 应返回 done 状态和文件名。"""
    app, dirs = app_ai_enabled
    name = "report-20260304-100000-to-20260304-120000.md"

    with patch("daily_reporter.ai.generate_full_report", return_value="# AI 结果"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(f"/api/reports/{name}/ai")
            assert r.status_code == 202

            # 等待后台任务完成
            await asyncio.sleep(0.5)

            r2 = await c.get("/api/reports/ai-tasks")
            body = r2.json()

    assert body["ok"] is True
    tasks = body["tasks"]
    assert len(tasks) >= 1
    task = next(t for t in tasks if t["name"] == name)
    assert task["status"] == "done"
    assert task["filename"] == "report-20260304-100000-to-20260304-120000-ai.md"
    # AI 文件确实被写入了
    ai_file = dirs["out_dir"] / "report-20260304-100000-to-20260304-120000-ai.md"
    assert ai_file.exists()
    assert ai_file.read_text(encoding="utf-8") == "# AI 结果"


@pytest.mark.asyncio
async def test_ai_task_error(app_ai_enabled):
    """AI 生成失败时，ai-tasks 应返回 error 状态。"""
    app, _ = app_ai_enabled
    name = "report-20260304-100000-to-20260304-120000.md"

    with patch("daily_reporter.ai.generate_full_report", side_effect=RuntimeError("模型超时")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(f"/api/reports/{name}/ai")
            assert r.status_code == 202

            await asyncio.sleep(0.5)

            r2 = await c.get("/api/reports/ai-tasks")
            body = r2.json()

    task = next(t for t in body["tasks"] if t["name"] == name)
    assert task["status"] == "error"
    assert "模型超时" in task["error"]


@pytest.mark.asyncio
async def test_ai_resubmit_after_done(app_ai_enabled):
    """任务完成后可以重新提交。"""
    app, _ = app_ai_enabled
    name = "report-20260304-100000-to-20260304-120000.md"

    # 模拟已完成的任务
    import time
    reports_module._ai_tasks[name] = {
        "status": "done", "filename": "xxx-ai.md", "error": None, "start_time": time.time()
    }

    with patch("daily_reporter.ai.generate_full_report", return_value="# 新 AI 版本"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(f"/api/reports/{name}/ai")

    # 已完成的任务可以重新提交
    assert r.status_code == 202
