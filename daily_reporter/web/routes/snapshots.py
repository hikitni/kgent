# -*- coding: utf-8 -*-
"""快照相关 API 路由"""

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from daily_reporter.snapshot import (
    delete_snapshot,
    load_index,
    load_snapshot,
    load_snapshot_meta,
    take_snapshot,
)
from daily_reporter.utils import SNAP_ID_RE

from ..deps import get_config

router = APIRouter()

_SNAP_ID_RE = SNAP_ID_RE


def _validate_snap_id(snap_id: str) -> None:
    if not _SNAP_ID_RE.match(snap_id):
        raise HTTPException(status_code=400, detail="无效的 snap_id 格式")


# ---------------------------------------------------------------------------
# GET /api/snapshots
# ---------------------------------------------------------------------------

@router.get("")
async def list_snapshots(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    q: Optional[str] = Query(None, description="搜索关键词（匹配 ID / 标签）"),
):
    cfg = get_config()
    index = load_index(cfg)

    if q:
        q_lower = q.lower()
        index = [
            s for s in index
            if q_lower in s["id"].lower() or q_lower in s.get("label", "").lower()
        ]

    total = len(index)
    # 最新的排前面
    index_sorted = list(reversed(index))
    start = (page - 1) * size
    page_items = index_sorted[start : start + size]

    return {
        "ok": True,
        "total": total,
        "page": page,
        "size": size,
        "items": page_items,
    }


# ---------------------------------------------------------------------------
# POST /api/snapshots — 打快照
# ---------------------------------------------------------------------------

@router.post("")
async def create_snapshot(
    label: str = Body("manual", embed=True),
):
    cfg = get_config()
    try:
        snap = take_snapshot(cfg, label=label, trigger="web")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 返回元数据（不含 files，避免响应体过大）
    return {
        "ok": True,
        "id": snap["id"],
        "timestamp": snap["timestamp"],
        "label": snap["label"],
        "trigger": snap["trigger"],
        "file_count": snap["file_count"],
    }


# ---------------------------------------------------------------------------
# GET /api/snapshots/{snap_id}
# ---------------------------------------------------------------------------

@router.get("/{snap_id}")
async def get_snapshot(
    snap_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    q: Optional[str] = Query(None),
):
    _validate_snap_id(snap_id)
    cfg = get_config()

    try:
        snap = load_snapshot_meta(cfg, snap_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"快照不存在: {snap_id}")

    files = snap.get("files", {})
    file_items = list(files.items())

    # 按路径搜索
    if q:
        q_lower = q.lower()
        file_items = [(p, info) for p, info in file_items if q_lower in p.lower()]

    total_files = len(file_items)
    start = (page - 1) * size
    page_files = file_items[start : start + size]

    return {
        "ok": True,
        "id": snap["id"],
        "timestamp": snap["timestamp"],
        "label": snap.get("label", ""),
        "trigger": snap.get("trigger", ""),
        "file_count": snap.get("file_count", total_files),
        "files": {
            "total": total_files,
            "page": page,
            "size": size,
            "items": [
                {
                    "path": path,
                    "hash": info.get("hash", "")[:12],
                    "lines": len(info["lines"]) if info.get("lines") is not None else None,
                }
                for path, info in page_files
            ],
        },
    }


# ---------------------------------------------------------------------------
# DELETE /api/snapshots/{snap_id}
# ---------------------------------------------------------------------------

@router.delete("/{snap_id}")
async def remove_snapshot(snap_id: str):
    _validate_snap_id(snap_id)
    cfg = get_config()
    ok = delete_snapshot(cfg, snap_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"快照不存在或删除失败: {snap_id}")
    return {"ok": True, "deleted": snap_id}


# ---------------------------------------------------------------------------
# DELETE /api/snapshots — 批量删除
# ---------------------------------------------------------------------------

@router.delete("")
async def bulk_delete_snapshots(ids: list = Body(..., embed=True)):
    cfg = get_config()
    deleted = []
    failed = []
    for snap_id in ids:
        if not isinstance(snap_id, str) or not _SNAP_ID_RE.match(snap_id):
            failed.append(snap_id)
            continue
        ok = delete_snapshot(cfg, snap_id)
        (deleted if ok else failed).append(snap_id)
    return {"ok": True, "deleted": deleted, "failed": failed}
