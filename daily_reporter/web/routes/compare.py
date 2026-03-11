# -*- coding: utf-8 -*-
"""快照对比 API 路由"""

from fastapi import APIRouter, HTTPException

from daily_reporter.diff import diff_snapshots, summarize_diff
from daily_reporter.snapshot import load_snapshot
from daily_reporter.utils import SNAP_ID_RE

from ..deps import get_config

router = APIRouter()

_SNAP_ID_RE = SNAP_ID_RE


def _validate_snap_id(snap_id: str) -> None:
    if not _SNAP_ID_RE.match(snap_id):
        raise HTTPException(status_code=400, detail=f"无效的 snap_id: {snap_id}")


@router.get("/{snap_a}/{snap_b}")
async def compare_snapshots(snap_a: str, snap_b: str):
    _validate_snap_id(snap_a)
    _validate_snap_id(snap_b)

    if snap_a == snap_b:
        raise HTTPException(status_code=400, detail="起点与终点快照相同，无变更")

    cfg = get_config()

    try:
        sa = load_snapshot(cfg, snap_a)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"快照不存在: {snap_a}")

    try:
        sb = load_snapshot(cfg, snap_b)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"快照不存在: {snap_b}")

    diffs = diff_snapshots(sa, sb)
    summary = summarize_diff(diffs)

    return {
        "ok": True,
        "snap_a": {
            "id": sa["id"],
            "timestamp": sa["timestamp"],
            "label": sa.get("label", ""),
        },
        "snap_b": {
            "id": sb["id"],
            "timestamp": sb["timestamp"],
            "label": sb.get("label", ""),
        },
        "summary": {
            "total": summary["total"],
            "created": len(summary["created"]),
            "modified": len(summary["modified"]),
            "deleted": len(summary["deleted"]),
            "total_add": summary["total_add"],
            "total_remove": summary["total_remove"],
            "net": summary["net"],
            "top_ext": summary["top_ext"],
            "top_dir": summary["top_dir"],
        },
        "diffs": [
            {
                "path": d["path"],
                "status": d["status"],
                "added_lines": d["added_lines"],
                "removed_lines": d["removed_lines"],
            }
            for d in diffs
        ],
    }
