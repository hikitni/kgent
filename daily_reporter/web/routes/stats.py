# -*- coding: utf-8 -*-
"""统计聚合 API 路由 — 为 Dashboard 可视化提供数据"""

import datetime as dt
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Query

from daily_reporter.diff import diff_snapshots, summarize_diff
from daily_reporter.snapshot import load_index, load_snapshot

from ..deps import get_config

router = APIRouter()


@router.get("/activity")
async def get_activity_stats(
    days: int = Query(90, ge=7, le=365, description="统计天数"),
):
    """
    返回活动统计数据，用于日历热力图和变更趋势折线图。

    - heatmap: [{date, count, file_count}]  — 按天聚合的快照活动
    - trend:   [{date, added, removed, net, snapshots}] — 按天聚合的代码变更
    - hourly:  [{hour, count}]  — 按小时聚合的快照分布
    """
    cfg = get_config()
    index = load_index(cfg)

    cutoff = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")

    # ---------- 按日聚合快照 ----------
    daily_snaps: dict[str, list] = defaultdict(list)
    for entry in index:
        # timestamp: "2026-03-04T12:37:00"
        date_str = entry["timestamp"][:10]
        if date_str < cutoff:
            continue
        daily_snaps[date_str].append(entry)

    # ---------- 热力图数据 ----------
    heatmap = []
    for date_str in sorted(daily_snaps.keys()):
        snaps = daily_snaps[date_str]
        total_files = sum(s.get("file_count", 0) for s in snaps)
        heatmap.append({
            "date": date_str,
            "count": len(snaps),
            "file_count": total_files,
        })

    # ---------- 变更趋势（相邻快照 diff）----------
    # 选取在时间范围内的快照 ID（按时间排序）
    recent_entries = []
    for entry in index:
        date_str = entry["timestamp"][:10]
        if date_str >= cutoff:
            recent_entries.append(entry)

    daily_changes: dict[str, dict] = defaultdict(lambda: {
        "added": 0, "removed": 0, "net": 0, "snapshots": 0
    })

    # 对相邻快照进行 diff（限制最大计算量，避免慢请求）
    max_pairs = min(len(recent_entries) - 1, 100)
    for i in range(max_pairs):
        entry_a = recent_entries[i]
        entry_b = recent_entries[i + 1]
        date_str = entry_b["timestamp"][:10]

        try:
            snap_a = load_snapshot(cfg, entry_a["id"])
            snap_b = load_snapshot(cfg, entry_b["id"])
            diffs = diff_snapshots(snap_a, snap_b)
            summary = summarize_diff(diffs)

            daily_changes[date_str]["added"] += summary["total_add"]
            daily_changes[date_str]["removed"] += summary["total_remove"]
            daily_changes[date_str]["net"] += summary["net"]
            daily_changes[date_str]["snapshots"] += 1
        except Exception:
            continue

    trend = []
    for date_str in sorted(daily_changes.keys()):
        trend.append({"date": date_str, **daily_changes[date_str]})

    # ---------- 小时分布 ----------
    hourly_counts = defaultdict(int)
    for entry in recent_entries:
        # timestamp: "2026-03-04T12:37:00"
        hour = int(entry["timestamp"][11:13])
        hourly_counts[hour] += 1

    hourly = [{"hour": h, "count": hourly_counts.get(h, 0)} for h in range(24)]

    return {
        "ok": True,
        "days": days,
        "heatmap": heatmap,
        "trend": trend,
        "hourly": hourly,
    }
