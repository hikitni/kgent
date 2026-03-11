#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地文件变更监控与日报生成（快照对比版）
用法：
  python daily_change_reporter.py snapshot [--label LABEL] [--config CONFIG]
  python daily_change_reporter.py list [--config CONFIG]
  python daily_change_reporter.py report [--from SNAP_ID] [--to SNAP_ID] [--config CONFIG]
  python daily_change_reporter.py watch [--config CONFIG]
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    watch_paths: List[Path]
    ignore_dirs: Set[str] = field(default_factory=set)
    ignore_suffixes: Set[str] = field(default_factory=set)
    ignore_patterns: List[str] = field(default_factory=list)
    snapshot_root: Path = Path(".daily_reporter")
    output_root: Path = Path("reports")
    encoding: str = "utf-8"
    auto_snapshot_times: List[str] = field(default_factory=list)  # ["06:00", "18:00"]
    max_file_size_kb: int = 1024  # 超过此大小只记录哈希，不存行内容


def load_config(config_path: Path) -> AppConfig:
    if not config_path.exists():
        raise SystemExit(f"[错误] 配置文件不存在: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    watch_paths_raw = raw.get("watch_paths", [])
    if not watch_paths_raw:
        raise SystemExit("[错误] watch_paths 不能为空")
    watch_paths = [Path(p).expanduser().resolve() for p in watch_paths_raw]
    return AppConfig(
        watch_paths=watch_paths,
        ignore_dirs=set(raw.get("ignore_dirs", [])),
        ignore_suffixes=set(raw.get("ignore_suffixes", [])),
        ignore_patterns=list(raw.get("ignore_patterns", [])),
        snapshot_root=Path(raw.get("snapshot_root", ".daily_reporter")).resolve(),
        output_root=Path(raw.get("output_root", "reports")).resolve(),
        encoding=raw.get("encoding", "utf-8"),
        auto_snapshot_times=list(raw.get("auto_snapshot_times", [])),
        max_file_size_kb=int(raw.get("max_file_size_kb", 1024)),
    )


# ---------------------------------------------------------------------------
# 快照
# ---------------------------------------------------------------------------

def _snap_id(ts: dt.datetime) -> str:
    return ts.strftime("%Y%m%d-%H%M%S")

def _snap_filename(snap_id: str) -> str:
    return f"snapshot-{snap_id}.json"

def _index_path(cfg: AppConfig) -> Path:
    return cfg.snapshot_root / "index.json"

def _snapshots_dir(cfg: AppConfig) -> Path:
    return cfg.snapshot_root / "snapshots"

def _load_index(cfg: AppConfig) -> List[dict]:
    idx = _index_path(cfg)
    if not idx.exists():
        return []
    with idx.open("r", encoding="utf-8") as f:
        return json.load(f)

def _save_index(cfg: AppConfig, index: List[dict]) -> None:
    _index_path(cfg).parent.mkdir(parents=True, exist_ok=True)
    with _index_path(cfg).open("w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

def _should_ignore(path: Path, cfg: AppConfig) -> bool:
    if any(part in cfg.ignore_dirs for part in path.parts):
        return True
    if path.suffix.lower() in cfg.ignore_suffixes:
        return True
    for pat in cfg.ignore_patterns:
        if re.search(pat, str(path)):
            return True
    return False

def _read_file_content(path: Path, cfg: AppConfig) -> Tuple[Optional[List[str]], str]:
    if not path.exists() or not path.is_file():
        return None, ""
    try:
        size_kb = path.stat().st_size / 1024
        if size_kb > cfg.max_file_size_kb:
            raw = path.read_bytes()
            return None, hashlib.md5(raw).hexdigest()
        content = path.read_text(encoding=cfg.encoding, errors="ignore")
        lines = content.splitlines()
        md5 = hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()
        return lines, md5
    except Exception:
        return None, ""

def take_snapshot(cfg: AppConfig, label: str = "manual", trigger: str = "manual") -> dict:
    now = dt.datetime.now()
    snap_id = _snap_id(now)
    files: Dict[str, dict] = {}
    for watch_path in cfg.watch_paths:
        if not watch_path.exists():
            print(f"  [跳过] 目录不存在: {watch_path}")
            continue
        for p in watch_path.rglob("*"):
            if not p.is_file():
                continue
            if _should_ignore(p, cfg):
                continue
            lines, md5 = _read_file_content(p, cfg)
            files[str(p)] = {"hash": md5, "lines": lines}
    snapshot = {
        "id": snap_id,
        "timestamp": now.isoformat(timespec="seconds"),
        "label": label,
        "trigger": trigger,
        "file_count": len(files),
        "files": files,
    }
    snap_dir = _snapshots_dir(cfg)
    snap_dir.mkdir(parents=True, exist_ok=True)
    with (snap_dir / _snap_filename(snap_id)).open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)
    index = _load_index(cfg)
    index.append({
        "id": snap_id,
        "timestamp": now.isoformat(timespec="seconds"),
        "label": label,
        "trigger": trigger,
        "file_count": len(files),
    })
    _save_index(cfg, index)
    return snapshot

def load_snapshot(cfg: AppConfig, snap_id: str) -> dict:
    snap_file = _snapshots_dir(cfg) / _snap_filename(snap_id)
    if not snap_file.exists():
        raise SystemExit(f"[错误] 快照不存在: {snap_id}")
    with snap_file.open("r", encoding="utf-8") as f:
        return json.load(f)

def list_snapshots(cfg: AppConfig) -> None:
    index = _load_index(cfg)
    if not index:
        print("暂无快照。请先执行: python daily_change_reporter.py snapshot")
        return
    print(f"\n{'序号':<6}{'ID':<20}{'时间':<22}{'标签':<12}{'触发方式':<10}{'文件数'}")
    print("-" * 76)
    for i, item in enumerate(index, 1):
        print(f"{i:<6}{item['id']:<20}{item['timestamp']:<22}{item['label']:<12}"
              f"{item['trigger']:<10}{item.get('file_count', '-')}")
    print()


# ---------------------------------------------------------------------------
# 对比
# ---------------------------------------------------------------------------

def diff_snapshots(snap_a: dict, snap_b: dict) -> List[dict]:
    files_a: dict = snap_a.get("files", {})
    files_b: dict = snap_b.get("files", {})
    results = []
    for path in sorted(set(files_a) | set(files_b)):
        in_a, in_b = path in files_a, path in files_b
        fa = files_a.get(path, {})
        fb = files_b.get(path, {})
        if in_a and not in_b:
            status = "deleted"
        elif not in_a and in_b:
            status = "created"
        elif fa.get("hash") == fb.get("hash"):
            continue
        else:
            status = "modified"
        lines_a: List[str] = fa.get("lines") or []
        lines_b: List[str] = fb.get("lines") or []
        set_a, set_b = set(lines_a), set(lines_b)
        added   = len([l for l in lines_b if l not in set_a])
        removed = len([l for l in lines_a if l not in set_b])
        results.append({
            "path": path, "status": status,
            "added_lines": added, "removed_lines": removed,
            "net_lines": added - removed,
        })
    return results


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def generate_report(cfg: AppConfig, snap_a: dict, snap_b: dict) -> Path:
    diffs    = diff_snapshots(snap_a, snap_b)
    ts_a     = snap_a["timestamp"]
    ts_b     = snap_b["timestamp"]
    id_a     = snap_a["id"]
    id_b     = snap_b["id"]
    label_a  = snap_a.get("label", "")
    label_b  = snap_b.get("label", "")

    created  = [d for d in diffs if d["status"] == "created"]
    modified = [d for d in diffs if d["status"] == "modified"]
    deleted  = [d for d in diffs if d["status"] == "deleted"]
    total_add    = sum(d["added_lines"]   for d in diffs)
    total_remove = sum(d["removed_lines"] for d in diffs)

    by_ext: Dict[str, int] = {}
    by_dir: Dict[str, int] = {}
    for d in diffs:
        ext = Path(d["path"]).suffix.lower() or "[无后缀]"
        by_ext[ext] = by_ext.get(ext, 0) + 1
        by_dir[str(Path(d["path"]).parent)] = by_dir.get(str(Path(d["path"]).parent), 0) + 1
    top_ext = sorted(by_ext.items(), key=lambda x: x[1], reverse=True)[:5]
    top_dir = sorted(by_dir.items(), key=lambda x: x[1], reverse=True)[:5]

    def file_rows(items: List[dict], max_show: int = 20) -> str:
        rows = [f"  - `{d['path']}` (+{d['added_lines']} / -{d['removed_lines']})"
                for d in items[:max_show]]
        if len(items) > max_show:
            rows.append(f"  - ...（共 {len(items)} 个，仅展示前 {max_show} 个）")
        return "\n".join(rows) if rows else "  （无）"

    lines = [
        "# 工作日报", "",
        f"- **快照起点**：{ts_a}（{label_a} / `{id_a}`）",
        f"- **快照终点**：{ts_b}（{label_b} / `{id_b}`）",
        f"- **生成时间**：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "", "---", "",
        "## 一、今日概览", "",
        "| 指标 | 数值 |", "|---|---|",
        f"| 变更文件总数 | {len(diffs)} |",
        f"| 新增文件 | {len(created)} |",
        f"| 修改文件 | {len(modified)} |",
        f"| 删除文件 | {len(deleted)} |",
        f"| 新增代码行 | +{total_add} |",
        f"| 删除代码行 | -{total_remove} |",
        f"| 净变化行数 | {total_add - total_remove:+d} |",
        "", "## 二、高频变更文件类型", "",
        *[f"- `{e}`：{c} 个文件" for e, c in top_ext],
        "", "## 三、高频变更目录", "",
        *[f"- `{d}`：{c} 个文件" for d, c in top_dir],
        "", "## 四、新增文件", "", file_rows(created),
        "", "## 五、修改文件", "", file_rows(modified),
        "", "## 六、删除文件", "", file_rows(deleted),
        "", "## 七、工作总结（自动草稿，请补充）", "",
        f"今日共涉及 {len(diffs)} 个文件的变更，新增 {total_add} 行，"
        f"删除 {total_remove} 行，净变化 {total_add - total_remove:+d} 行。",
        f"主要工作集中于 {', '.join(e for e, _ in top_ext[:3])} 类文件。",
        "", "**今日完成**：", "- （请在此补充）",
        "", "**问题与风险**：", "- （请在此补充）",
        "", "**明日计划**：", "- （请在此补充）",
    ]
    cfg.output_root.mkdir(parents=True, exist_ok=True)
    out = cfg.output_root / f"report-{id_a}-to-{id_b}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# watch 模式（定时自动快照）
# ---------------------------------------------------------------------------

def _time_to_label(hm: str) -> str:
    h = int(hm.split(":")[0])
    if 5 <= h < 10:  return "morning"
    if 10 <= h < 14: return "noon"
    if 14 <= h < 19: return "afternoon"
    return "evening"

def run_watch(cfg: AppConfig) -> None:
    if not cfg.auto_snapshot_times:
        print("[提示] 未配置 auto_snapshot_times，watch 模式不会自动打快照。")
        print('  请在 config.json 中添加: "auto_snapshot_times": ["06:00", "18:00"]')
    print(f"Watch 已启动。自动快照时间: {cfg.auto_snapshot_times or '未配置'}，按 Ctrl+C 退出。")
    triggered_today: Set[str] = set()
    try:
        while True:
            now = dt.datetime.now()
            today = now.strftime("%Y-%m-%d")
            current_hm = now.strftime("%H:%M")
            for t in cfg.auto_snapshot_times:
                key = f"{today}-{t}"
                if current_hm == t and key not in triggered_today:
                    label = _time_to_label(t)
                    print(f"\n[{now.strftime('%H:%M:%S')}] 定时触发快照（{label}）...")
                    snap = take_snapshot(cfg, label=label, trigger="auto")
                    triggered_today.add(key)
                    print(f"  快照完成: {snap['id']}，共 {snap['file_count']} 个文件")
            if current_hm == "00:00":
                triggered_today = {k for k in triggered_today if k.startswith(today)}
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nWatch 已退出。")


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地文件变更监控 + 快照日报生成")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("snapshot", help="立即打一个快照")
    p.add_argument("--label", default="manual")
    p.add_argument("--config", default="config.json")

    p = sub.add_parser("list", help="列出所有快照")
    p.add_argument("--config", default="config.json")

    p = sub.add_parser("report", help="选两个快照生成日报")
    p.add_argument("--from", dest="from_id", default=None)
    p.add_argument("--to",   dest="to_id",   default=None)
    p.add_argument("--config", default="config.json")

    p = sub.add_parser("watch", help="持续运行，按配置时间自动打快照")
    p.add_argument("--config", default="config.json")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.command:
        print("请指定命令: snapshot / list / report / watch\n使用 -h 查看帮助。")
        return

    cfg = load_config(Path(args.config).resolve())

    if args.command == "snapshot":
        print(f"正在打快照（label={args.label}）...")
        snap = take_snapshot(cfg, label=args.label, trigger="manual")
        print(f"快照完成: {snap['id']}，共 {snap['file_count']} 个文件")

    elif args.command == "list":
        list_snapshots(cfg)

    elif args.command == "report":
        index = _load_index(cfg)
        if not index:
            raise SystemExit("[错误] 暂无快照，请先执行: python daily_change_reporter.py snapshot")
        from_id = args.from_id or (index[-2]["id"] if len(index) >= 2 else index[-1]["id"])
        if args.to_id:
            end_snap = load_snapshot(cfg, args.to_id)
        else:
            print("正在自动打日结快照...")
            end_snap = take_snapshot(cfg, label="report", trigger="report")
            print(f"日结快照: {end_snap['id']}，共 {end_snap['file_count']} 个文件")
        start_snap = load_snapshot(cfg, from_id)
        print(f"\n对比快照: {from_id}  {end_snap['id']}")
        out = generate_report(cfg, start_snap, end_snap)
        print(f"日报已生成: {out}")

    elif args.command == "watch":
        run_watch(cfg)


if __name__ == "__main__":
    main()
