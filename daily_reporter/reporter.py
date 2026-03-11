# -*- coding: utf-8 -*-
"""日报生成模块"""

import datetime as dt
from pathlib import Path
from typing import List, Optional

from .config import AppConfig
from .diff import diff_snapshots, summarize_diff

_STATUS_LABEL = {
    "created":  "🟢 新增",
    "modified": "🟡 修改",
    "deleted":  "🔴 删除",
}


def _file_rows(items: List[dict], max_show: int = 20) -> str:
    rows = [
        f"  - `{d['path']}` (+{d['added_lines']} / -{d['removed_lines']})"
        for d in items[:max_show]
    ]
    if len(items) > max_show:
        rows.append(f"  - ...（共 {len(items)} 个，仅展示前 {max_show} 个）")
    return "\n".join(rows) if rows else "  （无）"


def _diff_preview_block(d: dict) -> List[str]:
    """为单个文件返回 Markdown diff 块行列表。"""
    label = _STATUS_LABEL.get(d["status"], d["status"])
    fname = Path(d["path"]).name
    lines = [
        f"### {label} `{fname}`",
        f"> `{d['path']}`  —  +{d['added_lines']} / -{d['removed_lines']}",
        "",
    ]
    if d.get("large_file"):
        lines.append("_（大文件，仅存储哈希，无法展示行级 diff）_")
    elif d.get("diff_content"):
        lines.append("```diff")
        lines.extend(d["diff_content"])
        if len(d["diff_content"]) >= 60:
            lines.append("...（已达展示上限 60 行，完整内容请查看文件）")
        lines.append("```")
    else:
        lines.append("_（无内容变更或空文件）_")
    lines.append("")
    return lines


def generate_report(cfg: AppConfig, snap_a: dict, snap_b: dict) -> Path:
    """根据两个快照生成 Markdown 日报，返回输出文件路径。"""
    diffs   = diff_snapshots(snap_a, snap_b)
    summary = summarize_diff(diffs)

    id_a, id_b = snap_a["id"], snap_b["id"]
    ts_a, ts_b = snap_a["timestamp"], snap_b["timestamp"]
    label_a    = snap_a.get("label", "")
    label_b    = snap_b.get("label", "")

    s = summary

    # --- 变更预览章节（每个文件 diff 块） ---
    preview_lines: List[str] = []
    for d in diffs:
        preview_lines.extend(_diff_preview_block(d))

    lines = [
        "# 工作日报", "",
        f"- **快照起点**：{ts_a}（{label_a} / `{id_a}`）",
        f"- **快照终点**：{ts_b}（{label_b} / `{id_b}`）",
        f"- **生成时间**：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "", "---", "",
        "## 一、今日概览", "",
        "| 指标 | 数值 |", "|---|---|",
        f"| 变更文件总数 | {s['total']} |",
        f"| 新增文件 | {len(s['created'])} |",
        f"| 修改文件 | {len(s['modified'])} |",
        f"| 删除文件 | {len(s['deleted'])} |",
        f"| 新增代码行 | +{s['total_add']} |",
        f"| 删除代码行 | -{s['total_remove']} |",
        f"| 净变化行数 | {s['net']:+d} |",
        "", "## 二、高频变更文件类型", "",
        *([f"- `{e}`：{c} 个文件" for e, c in s["top_ext"]] or ["  （无）"]),
        "", "## 三、高频变更目录", "",
        *([f"- `{d}`：{c} 个文件" for d, c in s["top_dir"]] or ["  （无）"]),
        "", "## 四、新增文件", "", _file_rows(s["created"]),
        "", "## 五、修改文件", "", _file_rows(s["modified"]),
        "", "## 六、删除文件", "", _file_rows(s["deleted"]),
        "", "## 七、变更内容预览", "",
        *(["_（无文件变更）_"] if not diffs else preview_lines),
        "", "## 八、工作总结（自动草稿，请补充）", "",
        f"今日共涉及 {s['total']} 个文件的变更，"
        f"新增 {s['total_add']} 行，删除 {s['total_remove']} 行，"
        f"净变化 {s['net']:+d} 行。",
        f"主要工作集中于 {', '.join(e for e, _ in s['top_ext'][:3]) or '不明'} 类文件。",
        "", "**今日完成**：", "- （请在此补充）",
        "", "**问题与风险**：", "- （请在此补充）",
        "", "**明日计划**：", "- （请在此补充）",
    ]

    cfg.output_root.mkdir(parents=True, exist_ok=True)
    out = cfg.output_root / f"report-{id_a}-to-{id_b}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def ai_report_path(raw_path: Path) -> Path:
    """根据原始日报路径，返回对应的 AI 版日报路径（同目录，-ai 后缀）。"""
    return raw_path.with_name(raw_path.stem + "-ai" + raw_path.suffix)


# ---------------------------------------------------------------------------
# 日报列表与管理
# ---------------------------------------------------------------------------

def list_reports(cfg: AppConfig) -> List[dict]:
    """
    扫描 output_root 下所有 .md 文件，返回按修改时间降序的列表。
    每项包含：filename, path, size_kb, mtime, snap_a, snap_b, is_ai
    """
    if not cfg.output_root.exists():
        return []

    results = []
    for f in sorted(cfg.output_root.glob("*.md"),
                    key=lambda p: p.stat().st_mtime, reverse=True):
        stat = f.stat()
        stem = f.stem   # report-A-to-B  或  report-A-to-B-ai
        is_ai = stem.endswith("-ai")
        if is_ai:
            stem = stem[:-3]   # strip "-ai"
        parts = stem.split("-to-", 1)
        snap_a = parts[0].replace("report-", "", 1) if len(parts) == 2 else "-"
        snap_b = parts[1] if len(parts) == 2 else "-"
        results.append({
            "filename": f.name,
            "path":     f,
            "size_kb":  round(stat.st_size / 1024, 1),
            "mtime":    dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "snap_a":   snap_a,
            "snap_b":   snap_b,
            "is_ai":    is_ai,
        })
    return results


def delete_report(path: Path) -> bool:
    """删除指定日报文件，返回是否成功。"""
    try:
        if path.exists():
            path.unlink()
            return True
        return False
    except Exception:
        return False
