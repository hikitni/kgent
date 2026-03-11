# -*- coding: utf-8 -*-
"""快照对比模块"""

import difflib
from collections import Counter
from pathlib import Path
from typing import List

# 每个文件最多输出的 diff 行数（+/- 合计），超出则截断
_MAX_DIFF_LINES = 60


def _unified_diff_lines(lines_a: List[str], lines_b: List[str]) -> List[str]:
    """返回简化的 unified diff 行（跳过 ---/+++/@@ 头，保留 +/-/空格行）。"""
    raw = list(difflib.unified_diff(lines_a, lines_b, lineterm="", n=2))
    return [
        l for l in raw
        if not l.startswith(("---", "+++", "@@"))
    ][:_MAX_DIFF_LINES]


def diff_snapshots(snap_a: dict, snap_b: dict) -> List[dict]:
    """
    对比两个快照，返回变更文件列表。
    每项包含: path, status, added_lines, removed_lines, net_lines,
              diff_content(实际变更行), large_file(是否大文件跳过行内容)
    """
    files_a: dict = snap_a.get("files", {})
    files_b: dict = snap_b.get("files", {})

    results = []
    for path in sorted(set(files_a) | set(files_b)):
        in_a = path in files_a
        in_b = path in files_b
        fa = files_a.get(path, {})
        fb = files_b.get(path, {})

        if in_a and not in_b:
            status = "deleted"
        elif not in_a and in_b:
            status = "created"
        elif fa.get("hash") == fb.get("hash"):
            continue  # 未变更
        else:
            status = "modified"

        lines_a: List[str] = fa.get("lines") or []
        lines_b: List[str] = fb.get("lines") or []
        # 大文件：快照中 lines=null，只有哈希
        large_file = (in_a and fa.get("lines") is None) or (in_b and fb.get("lines") is None)

        # 使用 Counter 精确统计重复行的增删数量
        counter_a = Counter(lines_a)
        counter_b = Counter(lines_b)
        added   = sum((counter_b - counter_a).values())
        removed = sum((counter_a - counter_b).values())

        if large_file:
            diff_content: List[str] = []
        elif status == "created":
            diff_content = ["+" + l for l in lines_b[:_MAX_DIFF_LINES]]
        elif status == "deleted":
            diff_content = ["-" + l for l in lines_a[:_MAX_DIFF_LINES]]
        else:
            diff_content = _unified_diff_lines(lines_a, lines_b)

        results.append({
            "path":          path,
            "status":        status,
            "added_lines":   added,
            "removed_lines": removed,
            "net_lines":     added - removed,
            "ext":           Path(path).suffix.lower() or "[无后缀]",
            "parent":        str(Path(path).parent),
            "diff_content":  diff_content,
            "large_file":    large_file,
        })

    return results


def summarize_diff(diffs: List[dict]) -> dict:
    """将 diff 列表聚合为摘要字典，供 UI 和 Reporter 共用。"""
    created  = [d for d in diffs if d["status"] == "created"]
    modified = [d for d in diffs if d["status"] == "modified"]
    deleted  = [d for d in diffs if d["status"] == "deleted"]

    total_add    = sum(d["added_lines"]   for d in diffs)
    total_remove = sum(d["removed_lines"] for d in diffs)

    by_ext: dict = {}
    by_dir: dict = {}
    for d in diffs:
        by_ext[d["ext"]]    = by_ext.get(d["ext"], 0) + 1
        by_dir[d["parent"]] = by_dir.get(d["parent"], 0) + 1

    return {
        "total":         len(diffs),
        "created":       created,
        "modified":      modified,
        "deleted":       deleted,
        "total_add":     total_add,
        "total_remove":  total_remove,
        "net":           total_add - total_remove,
        "top_ext":       sorted(by_ext.items(), key=lambda x: x[1], reverse=True)[:5],
        "top_dir":       sorted(by_dir.items(), key=lambda x: x[1], reverse=True)[:5],
    }
