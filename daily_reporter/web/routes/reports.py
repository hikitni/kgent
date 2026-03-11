# -*- coding: utf-8 -*-
"""日报相关 API 路由"""

import asyncio
import re
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse

from daily_reporter.config import load_config
from daily_reporter.reporter import (
    ai_report_path,
    delete_report,
    generate_report,
    list_reports,
)
from daily_reporter.snapshot import load_snapshot

from ..deps import get_config, get_config_path

router = APIRouter()

_REPORT_NAME_RE = re.compile(r"^report-[\w-]+\.md$")

# ---------------------------------------------------------------------------
# AI 异步任务池（内存级）
# ---------------------------------------------------------------------------
# key = 原始日报文件名
# value = {"status": "running"|"done"|"error", "filename": str|None, "error": str|None, "start_time": float}
_ai_tasks: dict[str, dict] = {}


def _validate_report_name(name: str) -> None:
    if not _REPORT_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="无效的日报文件名")


def _find_report_path(cfg, name: str) -> Path:
    path = cfg.output_root / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"日报不存在: {name}")
    return path


# ---------------------------------------------------------------------------
# GET /api/reports
# ---------------------------------------------------------------------------

@router.get("")
async def list_reports_api(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    type: Optional[str] = Query("all", pattern="^(all|ai|raw)$"),
):
    cfg = get_config()
    reports = list_reports(cfg)

    if type == "ai":
        reports = [r for r in reports if r.get("is_ai")]
    elif type == "raw":
        reports = [r for r in reports if not r.get("is_ai")]

    total = len(reports)
    start = (page - 1) * size
    page_items = reports[start : start + size]

    # path 是 Path 对象，序列化为字符串
    serialized = [
        {k: (str(v) if isinstance(v, Path) else v) for k, v in r.items()}
        for r in page_items
    ]

    return {"ok": True, "total": total, "page": page, "size": size, "items": serialized}


# ---------------------------------------------------------------------------
# GET /api/reports/ai-tasks — 查询 AI 任务状态（必须在 /{name} 之前注册）
# ---------------------------------------------------------------------------

@router.get("/ai-tasks")
async def list_ai_tasks():
    now = time.time()
    tasks = []
    for name, t in _ai_tasks.items():
        tasks.append({
            "name": name,
            "status": t["status"],
            "filename": t["filename"],
            "error": t["error"],
            "elapsed_sec": round(now - t["start_time"], 1),
        })
    return {"ok": True, "tasks": tasks}


# ---------------------------------------------------------------------------
# POST /api/reports/generate — 生成日报（必须在 /{name} 之前注册）
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_report_api(
    snap_a: str = Body(..., embed=True),
    snap_b: str = Body(..., embed=True),
):
    cfg = get_config()
    try:
        sa = load_snapshot(cfg, snap_a)
        sb = load_snapshot(cfg, snap_b)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        out = await asyncio.to_thread(generate_report, cfg, sa, sb)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "ok": True,
        "filename": out.name,
        "path": str(out),
        "snap_a": snap_a,
        "snap_b": snap_b,
    }


# ---------------------------------------------------------------------------
# GET /api/reports/{name}/content
# ---------------------------------------------------------------------------

@router.get("/{name}/content")
async def get_report_content(name: str):
    _validate_report_name(name)
    cfg = get_config()
    path = _find_report_path(cfg, name)
    content = path.read_text(encoding="utf-8")
    return {"ok": True, "filename": name, "content": content}


# ---------------------------------------------------------------------------
# POST /api/reports/{name}/ai — AI 异步生成
# ---------------------------------------------------------------------------

async def _run_ai_task(name: str, cfg, path: Path) -> None:
    """后台协程：执行 AI 全文重写，完成后更新 _ai_tasks。"""
    try:
        from daily_reporter.ai import generate_full_report

        raw_text = path.read_text(encoding="utf-8")
        ai_text = await asyncio.to_thread(generate_full_report, cfg, raw_text)
        out = ai_report_path(path)
        out.write_text(ai_text, encoding="utf-8")
        _ai_tasks[name]["status"] = "done"
        _ai_tasks[name]["filename"] = out.name
    except Exception as e:
        _ai_tasks[name]["status"] = "error"
        _ai_tasks[name]["error"] = str(e)


@router.post("/{name}/ai")
async def generate_ai_report(name: str):
    _validate_report_name(name)
    if name.endswith("-ai.md"):
        raise HTTPException(status_code=400, detail="已是 AI 日报，无需再次生成")

    cfg = get_config()
    if cfg.ai_provider.lower() == "disabled":
        raise HTTPException(status_code=503, detail="AI Provider 未配置，请设置 config.json 中的 ai_provider")

    path = _find_report_path(cfg, name)

    # 防止重复提交
    existing = _ai_tasks.get(name)
    if existing and existing["status"] == "running":
        return JSONResponse(
            {"ok": False, "detail": "该日报正在生成 AI 版本，请勿重复提交"},
            status_code=409,
        )

    # 注册任务并启动后台协程
    _ai_tasks[name] = {
        "status": "running",
        "filename": None,
        "error": None,
        "start_time": time.time(),
    }
    asyncio.create_task(_run_ai_task(name, cfg, path))

    return JSONResponse(
        {"ok": True, "task_id": name, "status": "running"},
        status_code=202,
    )


# ---------------------------------------------------------------------------
# DELETE /api/reports/{name}
# ---------------------------------------------------------------------------

@router.delete("/{name}")
async def remove_report(name: str):
    _validate_report_name(name)
    cfg = get_config()
    path = _find_report_path(cfg, name)
    ok = delete_report(path)
    if not ok:
        raise HTTPException(status_code=500, detail="删除失败")
    return {"ok": True, "deleted": name}
