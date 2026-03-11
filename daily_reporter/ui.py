# -*- coding: utf-8 -*-
"""交互式终端界面（基于 rich）"""

import datetime as dt
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    from rich.text import Text
    from rich.prompt import Prompt, Confirm
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    raise SystemExit("[错误] 未安装 rich，请执行: pip install rich")

from .config import AppConfig, load_config
from .snapshot import take_snapshot, load_snapshot, load_index, delete_snapshot
from .diff import diff_snapshots, summarize_diff
from .reporter import generate_report, list_reports, delete_report, ai_report_path
from .utils import hm_to_label, paginate

console = Console()

# ---------------------------------------------------------------------------
# 公共辅助
# ---------------------------------------------------------------------------

def _clear() -> None:
    console.clear()


def _header(title: str) -> None:
    console.print(Panel(
        f"[bold cyan]{title}[/]",
        border_style="cyan",
        padding=(0, 2),
    ))


def _pick_snapshot(index: List[dict], prompt: str = "请选择快照序号") -> Optional[dict]:
    """展示快照列表（带分页），让用户按序号选择，返回选中项或 None。"""
    if not index:
        console.print("[yellow]暂无快照。[/]")
        return None

    page = 1
    page_size = 20
    while True:
        page_items, total_pages, page = _paginate(index, page, page_size)
        offset = (page - 1) * page_size
        _show_snapshot_table(page_items, offset=offset)
        console.print(
            f"[dim]第 {page}/{total_pages} 页，共 {len(index)} 条[/]  "
            "[dim]n=下页  p=上页[/]"
        )
        raw = Prompt.ask(f"\n[bold]{prompt}[/] (序号=选择，n=下页，p=上页，0=返回)").strip().lower()
        if raw == "0":
            return None
        if raw == "n":
            page = min(page + 1, total_pages)
            continue
        if raw == "p":
            page = max(page - 1, 1)
            continue
        if raw.isdigit():
            local_n = int(raw)
            global_idx = offset + local_n - 1
            if 1 <= local_n <= len(page_items) and global_idx < len(index):
                return index[global_idx]
        console.print("[red]无效序号，请重新输入。[/]")


def _show_snapshot_table(index: List[dict], offset: int = 0) -> None:
    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold magenta")
    t.add_column("序号", width=6, justify="right")
    t.add_column("ID", style="dim")
    t.add_column("时间", min_width=20)
    t.add_column("标签", style="cyan")
    t.add_column("触发", style="green")
    t.add_column("文件数", justify="right")
    for i, s in enumerate(index, 1 + offset):
        t.add_row(
            str(i),
            s["id"],
            s["timestamp"],
            s.get("label", "-"),
            s.get("trigger", "-"),
            str(s.get("file_count", "-")),
        )
    console.print(t)


def _paginate(items: list, page: int, page_size: int = 20):
    """将列表分页，返回 (当前页数据, 总页数, 实际页码)。"""
    return paginate(items, page, page_size)


# ---------------------------------------------------------------------------
# 各功能页面
# ---------------------------------------------------------------------------

def page_take_snapshot(cfg: AppConfig) -> None:
    _clear()
    _header("📸 打快照")
    label = Prompt.ask("[bold]快照标签[/]", default="manual")
    console.print(f"\n[dim]正在扫描监控目录...[/]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as prog:
        task = prog.add_task("扫描中...", total=None)
        snap = take_snapshot(cfg, label=label, trigger="manual")
        prog.update(task, description="完成")

    console.print(Panel(
        f"[green]✓ 快照已生成[/]\n\n"
        f"  ID：[bold]{snap['id']}[/]\n"
        f"  时间：{snap['timestamp']}\n"
        f"  标签：{snap['label']}\n"
        f"  文件数：{snap['file_count']}",
        border_style="green",
        title="结果",
    ))
    Prompt.ask("\n按 Enter 返回", default="")


def page_browse_snapshots(cfg: AppConfig) -> None:
    _clear()
    _header("📋 浏览 / 管理快照")

    index = load_index(cfg)
    if not index:
        console.print("[yellow]暂无快照。请先通过主菜单「1 打快照」创建一个。[/]")
        Prompt.ask("\n按 Enter 返回", default="")
        return

    page = 1
    page_size = 20
    while True:
        index = load_index(cfg)
        page_items, total_pages, page = _paginate(index, page, page_size)
        offset = (page - 1) * page_size
        _show_snapshot_table(page_items, offset=offset)
        console.print(
            f"[dim]第 {page}/{total_pages} 页，共 {len(index)} 条[/]"
        )
        console.print(
            "\n[bold]操作说明[/]\n"
            "  输入 [bold cyan]序号[/]（如 [bold]2[/]）      → 查看该快照详情（文件列表、哈希、行数）\n"
            "  输入 [bold red]d+序号[/]（如 [bold]d2[/]）   → 删除该快照（会二次确认）\n"
            "  输入 [bold]n[/] / [bold]p[/]           → 下一页 / 上一页\n"
            "  输入 [bold]0[/]                → 返回主菜单\n"
        )
        raw = Prompt.ask("[bold]请输入[/]", default="0").strip().lower()

        if raw == "0":
            return

        if raw == "n":
            page = min(page + 1, total_pages)
            continue

        if raw == "p":
            page = max(page - 1, 1)
            continue

        # 删除：d<N>
        if raw.startswith("d") and raw[1:].isdigit():
            local_n = int(raw[1:])
            global_idx = offset + local_n - 1
            if 1 <= local_n <= len(page_items) and global_idx < len(index):
                item = index[global_idx]
                console.print(
                    f"\n  将删除：[bold]{item['id']}[/]  {item['timestamp']}  [{item.get('label','-')}]"
                )
                confirmed = Confirm.ask(
                    f"[red]确认删除？此操作不可撤销[/]", default=False
                )
                if confirmed:
                    ok = delete_snapshot(cfg, item["id"])
                    console.print(
                        f"[green]✓ 已删除 {item['id']}[/]" if ok else "[red]删除失败。[/]"
                    )
                    # 删除后重置到第一页避免越界
                    page = 1
                else:
                    console.print("[dim]已取消。[/]")
            else:
                console.print(f"[red]序号超出范围，请输入 1 ~ {len(page_items)}（当前页）。[/]")
            continue

        # 查看详情：<N>
        if raw.isdigit():
            local_n = int(raw)
            global_idx = offset + local_n - 1
            if 1 <= local_n <= len(page_items) and global_idx < len(index):
                _show_snapshot_detail(cfg, index[global_idx])
            else:
                console.print(f"[red]序号超出范围，请输入 1 ~ {len(page_items)}（当前页）。[/]")
            continue

        console.print("[red]无效输入。请参考上方操作说明。[/]")


def _show_snapshot_detail(cfg: AppConfig, item: dict) -> None:
    _clear()
    _header(f"🔎 快照详情 — {item['id']}")
    try:
        snap = load_snapshot(cfg, item["id"])
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        Prompt.ask("\n按 Enter 返回", default="")
        return

    files = snap.get("files", {})
    console.print(Panel(
        f"  ID      : [bold]{snap['id']}[/]\n"
        f"  时间    : {snap['timestamp']}\n"
        f"  标签    : {snap.get('label', '-')}\n"
        f"  触发方式: {snap.get('trigger', '-')}\n"
        f"  文件数  : {snap.get('file_count', len(files))}",
        title="元数据",
        border_style="cyan",
        padding=(0, 2),
    ))

    # 展示前 30 个文件
    t = Table(box=box.MINIMAL, header_style="bold", show_header=True)
    t.add_column("文件路径", overflow="fold")
    t.add_column("哈希", width=14, style="dim")
    t.add_column("行数", justify="right")

    for path, info in list(files.items())[:30]:
        lines = info.get("lines")
        line_count = str(len(lines)) if lines is not None else "[dim]大文件[/]"
        t.add_row(path, info.get("hash", "")[:12], line_count)

    if len(files) > 30:
        console.print(f"[dim]（共 {len(files)} 个文件，展示前 30 条）[/]")
    console.print(t)
    Prompt.ask("\n按 Enter 返回", default="")


def page_compare_snapshots(cfg: AppConfig) -> None:
    _clear()
    _header("🔍 对比快照")

    index = load_index(cfg)
    if len(index) < 2:
        console.print("[yellow]至少需要 2 个快照才能对比。[/]")
        Prompt.ask("\n按 Enter 返回", default="")
        return

    console.print("[bold cyan]选择起点快照（A）[/]")
    snap_a_meta = _pick_snapshot(index, "起点快照序号")
    if not snap_a_meta:
        return

    console.print("\n[bold cyan]选择终点快照（B）[/]")
    snap_b_meta = _pick_snapshot(index, "终点快照序号")
    if not snap_b_meta:
        return

    if snap_a_meta["id"] == snap_b_meta["id"]:
        console.print("[yellow]起点与终点相同，无变更。[/]")
        Prompt.ask("\n按 Enter 返回", default="")
        return

    console.print(f"\n[dim]正在加载并对比快照...[/]")
    try:
        snap_a = load_snapshot(cfg, snap_a_meta["id"])
        snap_b = load_snapshot(cfg, snap_b_meta["id"])
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        Prompt.ask("\n按 Enter 返回", default="")
        return

    diffs   = diff_snapshots(snap_a, snap_b)
    summary = summarize_diff(diffs)
    _show_diff_summary(snap_a_meta, snap_b_meta, summary, diffs)


def _show_diff_summary(
    meta_a: dict, meta_b: dict,
    summary: dict, diffs: list
) -> None:
    s = summary

    # 概览面板
    console.print(Panel(
        f"[bold]起点[/]  {meta_a['timestamp']}（{meta_a.get('label', '-')}）\n"
        f"[bold]终点[/]  {meta_b['timestamp']}（{meta_b.get('label', '-')}）",
        title="对比区间",
        border_style="cyan",
    ))

    # 概览表
    t = Table(box=box.SIMPLE, header_style="bold")
    t.add_column("指标", style="bold")
    t.add_column("数值", justify="right")
    rows = [
        ("变更文件总数", str(s["total"])),
        ("新增文件",    f"[green]{len(s['created'])}[/]"),
        ("修改文件",    f"[yellow]{len(s['modified'])}[/]"),
        ("删除文件",    f"[red]{len(s['deleted'])}[/]"),
        ("新增行",      f"[green]+{s['total_add']}[/]"),
        ("删除行",      f"[red]-{s['total_remove']}[/]"),
        ("净变化行",    f"{s['net']:+d}"),
    ]
    for k, v in rows:
        t.add_row(k, v)
    console.print(t)

    # 高频文件类型
    if s["top_ext"]:
        console.print("[bold]高频文件类型：[/] " +
                      "  ".join(f"[cyan]{e}[/] {c}个" for e, c in s["top_ext"]))

    # 变更明细（分页展示）
    console.print()
    _show_diff_detail(diffs)

    # 是否生成日报在 page_report 里单独处理
    Prompt.ask("\n按 Enter 返回", default="")


def _show_diff_detail(diffs: list, max_per_status: int = 15) -> None:
    status_cfg = [
        ("created",  "green",  "新增文件"),
        ("modified", "yellow", "修改文件"),
        ("deleted",  "red",    "删除文件"),
    ]
    for status, color, label in status_cfg:
        items = [d for d in diffs if d["status"] == status]
        if not items:
            continue
        t = Table(
            title=f"[bold {color}]{label}（{len(items)} 个）[/]",
            box=box.MINIMAL,
            header_style="bold",
            show_header=True,
            title_justify="left",
        )
        t.add_column("文件路径", overflow="fold")
        t.add_column("+行", justify="right", style="green", width=6)
        t.add_column("-行", justify="right", style="red", width=6)
        for d in items[:max_per_status]:
            t.add_row(d["path"], str(d["added_lines"]), str(d["removed_lines"]))
        if len(items) > max_per_status:
            t.add_row(f"[dim]...共 {len(items)} 个，省略 {len(items)-max_per_status} 个[/]", "", "")
        console.print(t)


def page_generate_report(cfg: AppConfig) -> None:
    _clear()
    _header("📄 生成日报")

    index = load_index(cfg)
    if not index:
        console.print("[yellow]暂无快照，请先打快照。[/]")
        Prompt.ask("\n按 Enter 返回", default="")
        return

    # 默认取最后两个
    default_a = index[-2] if len(index) >= 2 else index[-1]
    default_b = index[-1]

    console.print(f"[dim]默认起点：{default_a['id']}（{default_a.get('label','-')}）[/]")
    console.print(f"[dim]默认终点：{default_b['id']}（{default_b.get('label','-')}）[/]")
    use_default = Confirm.ask("使用默认快照区间？", default=True)

    if use_default:
        snap_a_meta, snap_b_meta = default_a, default_b
    else:
        console.print("\n[bold cyan]选择起点快照（A）[/]")
        snap_a_meta = _pick_snapshot(index, "起点序号")
        if not snap_a_meta:
            return
        console.print("\n[bold cyan]选择终点快照（B）[/]")
        snap_b_meta = _pick_snapshot(index, "终点序号")
        if not snap_b_meta:
            return

    try:
        snap_a = load_snapshot(cfg, snap_a_meta["id"])
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        Prompt.ask("\n按 Enter 返回", default="")
        return

    try:
        snap_b = load_snapshot(cfg, snap_b_meta["id"])
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        Prompt.ask("\n按 Enter 返回", default="")
        return

    # 生成原始日报
    console.print(f"\n[dim]对比: {snap_a_meta['id']} → {snap_b_meta['id']}[/]")
    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  transient=True, console=console) as prog:
        t = prog.add_task("生成日报中...", total=None)
        raw_out = generate_report(cfg, snap_a, snap_b)
        prog.update(t, description="完成")

    ai_out: Optional[Path] = None

    # AI 日报（可选）
    if cfg.ai_provider.lower() != "disabled":
        if Confirm.ask("\n是否用 AI 生成口语化日报？", default=True):
            ai_out = _generate_ai_report(cfg, raw_out)
    else:
        console.print(
            "[dim]提示：在 config.json 中设置 ai_provider 可将变更数据投送 AI 生成口语化日报。[/]"
        )

    # 展示结果
    result_lines = [f"ℹ️  原始日报：[bold]{raw_out}[/]"]
    if ai_out:
        result_lines.append(f"✨  AI 日报：[bold]{ai_out}[/]")
    console.print(Panel(
        "[green]✓ 日报已生成[/]\n\n" + "\n".join(result_lines),
        border_style="green",
        title="结果",
    ))

    if Confirm.ask("是否立即打开日报文件？", default=True):
        if ai_out:
            _open_file(ai_out)
        else:
            _open_file(raw_out)

    Prompt.ask("\n按 Enter 返回", default="")


def _open_file(path: Path) -> None:
    """跨平台打开文件（Windows 用 os.startfile，其他系统用 xdg-open/open）。"""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        console.print(f"[dim]已请求系统打开：{path}[/]")
    except Exception as e:
        console.print(f"[red]无法自动打开文件：{e}[/]")
        console.print(f"[dim]请手动打开：{path}[/]")


def _generate_ai_report(cfg: AppConfig, raw_path: Path) -> Optional[Path]:
    """
    读取原始日报，用 AI 生成新版本，写入 <name>-ai.md。
    成功返回 AI 版路径，失败返回 None（原始文件不受影响）。
    """
    from .ai import generate_full_report

    template_info = ""
    if cfg.ai_prompt_template and cfg.ai_prompt_template.exists():
        template_info = f"（模板：{cfg.ai_prompt_template.name}）"

    console.print(
        f"\n[dim]正在调用 {cfg.ai_provider} ({cfg.ai_model or '默认模型'}) 生成 AI 日报 {template_info}...[/]"
    )
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as prog:
            task = prog.add_task("AI 生成中...", total=None)
            raw_text = raw_path.read_text(encoding="utf-8")
            ai_text  = generate_full_report(cfg, raw_text)
            out = ai_report_path(raw_path)
            out.write_text(ai_text, encoding="utf-8")
            prog.update(task, description="完成")

        console.print(f"[green]✓ AI 日报已生成：{out.name}[/]")
        return out
    except (ValueError, RuntimeError) as e:
        console.print(f"[yellow]⚠ AI 生成失败，已保留原始日报：{e}[/]")
    except Exception as e:
        console.print(f"[yellow]⚠ AI 生成失败，已保留原始日报：{e}[/]")
    return None


# 保留兼容名，旧代码调用不中断
def _rewrite_report_with_ai(cfg: AppConfig, report_path: Path) -> Optional[Path]:
    return _generate_ai_report(cfg, report_path)



def _run_ai_summary(cfg: AppConfig, report_path: Path) -> None:
    """调用 AI 总结日报，将结果追加到日报文件并在终端展示。"""
    from .ai import summarize_report, append_ai_summary

    console.print(f"\n[dim]正在调用 {cfg.ai_provider} ({cfg.ai_model or '默认模型'}) ...[/]")
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as prog:
            task = prog.add_task("AI 分析中...", total=None)
            report_text = report_path.read_text(encoding="utf-8")
            summary = summarize_report(cfg, report_text)
            append_ai_summary(report_path, summary, provider_name=cfg.ai_provider)
            prog.update(task, description="完成")

        console.print(Panel(
            f"{summary}\n\n[dim]已追加至日报第九章[/]",
            border_style="magenta",
            title=f"✨ AI 智能总结 ({cfg.ai_provider})",
            padding=(1, 2),
        ))
    except (ValueError, RuntimeError) as e:
        console.print(f"[red]AI 总结失败：{e}[/]")
    except Exception as e:
        console.print(f"[red]未预期错误：{e}[/]")


def page_watch(cfg: AppConfig) -> None:
    _clear()
    _header("⏱  Watch 模式（定时自动快照）")

    if not cfg.auto_snapshot_times:
        console.print(
            "[yellow]未配置 auto_snapshot_times，watch 模式不会自动打快照。[/]\n"
            "[dim]请在 config.json 中添加: \"auto_snapshot_times\": [\"06:00\", \"18:00\"][/]"
        )
        Prompt.ask("\n按 Enter 返回", default="")
        return

    console.print(f"自动快照时间：[bold]{cfg.auto_snapshot_times}[/]")
    console.print("[dim]按 Ctrl+C 退出 Watch 模式[/]\n")

    triggered_today: set = set()
    try:
        while True:
            now = dt.datetime.now()
            today = now.strftime("%Y-%m-%d")
            current_hm = now.strftime("%H:%M")

            for t in cfg.auto_snapshot_times:
                key = f"{today}-{t}"
                if current_hm == t and key not in triggered_today:
                    label = _time_to_label(t)
                    console.print(
                        f"[{now.strftime('%H:%M:%S')}] [cyan]定时触发快照[/]（{label}）..."
                    )
                    snap = take_snapshot(cfg, label=label, trigger="auto")
                    triggered_today.add(key)
                    console.print(
                        f"  [green]✓[/] 快照 {snap['id']}，{snap['file_count']} 个文件"
                    )

            if current_hm == "00:00":
                triggered_today = {k for k in triggered_today if k.startswith(today)}

            time.sleep(30)

    except KeyboardInterrupt:
        console.print("\n[yellow]Watch 已退出。[/]")
        Prompt.ask("\n按 Enter 返回", default="")


def _time_to_label(hm: str) -> str:
    return hm_to_label(hm)


# ---------------------------------------------------------------------------
# 配置查看页
# ---------------------------------------------------------------------------

def page_view_config(cfg: AppConfig, config_path: Path) -> None:
    _clear()
    _header("⚙️  查看配置")

    # 原始 JSON（可能被用户手动编辑，直接读文件展示最新内容）
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[red]读取配置失败：{e}[/]")
        Prompt.ask("\n按 Enter 返回", default="")
        return

    console.print(Panel(
        f"配置文件路径：[bold]{config_path}[/]",
        border_style="cyan",
    ))

    # --- 监控目录 ---
    t1 = Table(title="监控目录 watch_paths", box=box.SIMPLE, title_justify="left",
               header_style="bold magenta")
    t1.add_column("路径", overflow="fold")
    for p in raw.get("watch_paths", []):
        t1.add_row(p)
    console.print(t1)

    # --- 快照 / 输出 / 大小限制 ---
    t2 = Table(title="存储设置", box=box.SIMPLE, title_justify="left",
               header_style="bold magenta")
    t2.add_column("键", style="bold")
    t2.add_column("值")
    t2.add_row("snapshot_root",   str(raw.get("snapshot_root", "-")))
    t2.add_row("output_root",     str(raw.get("output_root", "-")))
    t2.add_row("max_file_size_kb",str(raw.get("max_file_size_kb", "-")))
    t2.add_row("encoding",        str(raw.get("encoding", "utf-8")))
    console.print(t2)

    # --- 自动快照时间 ---
    t3 = Table(title="自动快照时间 auto_snapshot_times", box=box.SIMPLE,
               title_justify="left", header_style="bold magenta")
    t3.add_column("时间点")
    for tm in raw.get("auto_snapshot_times", []):
        t3.add_row(tm)
    if not raw.get("auto_snapshot_times"):
        t3.add_row("[dim]（未配置）[/]")
    console.print(t3)

    # --- 忽略规则 ---
    t4 = Table(title="忽略规则", box=box.SIMPLE, title_justify="left",
               header_style="bold magenta")
    t4.add_column("类型", style="cyan", width=18)
    t4.add_column("内容", overflow="fold")
    for d in raw.get("ignore_dirs", []):
        t4.add_row("ignore_dirs", d)
    for s in raw.get("ignore_suffixes", []):
        t4.add_row("ignore_suffixes", s)
    for p in raw.get("ignore_patterns", []):
        t4.add_row("ignore_patterns", p)
    console.print(t4)

    console.print()
    action = Prompt.ask(
        "[bold]操作[/]: [o] 用系统编辑器打开配置文件  [0] 返回",
        default="0"
    ).strip().lower()
    if action == "o":
        _open_file(config_path)
        Prompt.ask("\n按 Enter 返回", default="")


# ---------------------------------------------------------------------------
# 日报管理页
# ---------------------------------------------------------------------------

def page_manage_reports(cfg: AppConfig) -> None:
    _clear()
    _header("📑 日报管理")

    page = 1
    page_size = 20
    while True:
        reports = list_reports(cfg)
        if not reports:
            console.print(
                "[yellow]暂无日报。请通过主菜单「4 生成日报」生成第一份日报。[/]"
            )
            Prompt.ask("\n按 Enter 返回", default="")
            return

        page_items, total_pages, page = _paginate(reports, page, page_size)
        offset = (page - 1) * page_size

        # 展示当前页日报列表
        t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold magenta")
        t.add_column("序号", width=6, justify="right")
        t.add_column("类型", width=6)
        t.add_column("文件名", overflow="fold")
        t.add_column("生成时间", min_width=16)
        t.add_column("起点快照", style="dim")
        t.add_column("终点快照", style="dim")
        t.add_column("大小", justify="right")
        for i, r in enumerate(page_items, 1 + offset):
            badge = "[magenta]AI[/]" if r.get("is_ai") else "[dim]原始[/]"
            t.add_row(
                str(i),
                badge,
                r["filename"],
                r["mtime"],
                r["snap_a"],
                r["snap_b"],
                f"{r['size_kb']} KB",
            )
        console.print(t)
        console.print(
            f"[dim]第 {page}/{total_pages} 页，共 {len(reports)} 条[/]"
        )

        console.print(
            "\n[bold]操作说明[/]\n"
            "  输入 [bold cyan]序号[/]（如 [bold]2[/]）     → 打开该日报文件\n"
            "  输入 [bold magenta]s+序号[/]（如 [bold]s2[/]）  → 用 AI 生成该日报对应的 AI 版\n"
            "  输入 [bold red]d+序号[/]（如 [bold]d2[/]）  → 删除该日报（会二次确认）\n"
            "  输入 [bold]n[/] / [bold]p[/]          → 下一页 / 上一页\n"
            "  输入 [bold]0[/]               → 返回主菜单\n"
        )
        raw = Prompt.ask("[bold]请输入[/]", default="0").strip().lower()

        if raw == "0":
            return

        if raw == "n":
            page = min(page + 1, total_pages)
            continue

        if raw == "p":
            page = max(page - 1, 1)
            continue

        # AI 生成：s<N> — 将原始日报投送 AI，生成对应的 AI 版文件
        if raw.startswith("s") and raw[1:].isdigit():
            local_n = int(raw[1:])
            global_idx = offset + local_n - 1
            if 1 <= local_n <= len(page_items) and global_idx < len(reports):
                r = reports[global_idx]
                if cfg.ai_provider.lower() == "disabled":
                    console.print(
                        "[yellow]未启用 AI Provider。请先在 config.json 中设置 ai_provider。[/]"
                    )
                else:
                    # s+N 总是基于原始版生成，如果点的就是 AI 版则找对应原始版
                    source_path = r["path"]
                    if r.get("is_ai"):
                        raw_path = source_path.with_name(
                            source_path.stem[:-3] + source_path.suffix  # strip -ai
                        )
                        if raw_path.exists():
                            source_path = raw_path
                    ai_out = _generate_ai_report(cfg, source_path)
                    if ai_out:
                        Prompt.ask("\n按 Enter 继续", default="")
            else:
                console.print(f"[red]序号超出范围，请输入 1 ~ {len(page_items)}（当前页）。[/]")
            continue

        # 删除：d<N>
        if raw.startswith("d") and raw[1:].isdigit():
            local_n = int(raw[1:])
            global_idx = offset + local_n - 1
            if 1 <= local_n <= len(page_items) and global_idx < len(reports):
                r = reports[global_idx]
                console.print(f"\n  将删除：[bold]{r['filename']}[/]  ({r['mtime']})")
                if Confirm.ask("[red]确认删除？此操作不可撤销[/]", default=False):
                    ok = delete_report(r["path"])
                    console.print(
                        f"[green]✓ 已删除 {r['filename']}[/]" if ok else "[red]删除失败。[/]"
                    )
                    # 删除后重置到第一页避免越界
                    page = 1
                else:
                    console.print("[dim]已取消。[/]")
            else:
                console.print(f"[red]序号超出范围，请输入 1 ~ {len(page_items)}（当前页）。[/]")
            continue

        # 打开：<N>
        if raw.isdigit():
            local_n = int(raw)
            global_idx = offset + local_n - 1
            if 1 <= local_n <= len(page_items) and global_idx < len(reports):
                _open_file(reports[global_idx]["path"])
                Prompt.ask("[dim]已请求系统打开，按 Enter 继续[/]", default="")
            else:
                console.print(f"[red]序号超出范围，请输入 1 ~ {len(page_items)}（当前页）。[/]")
            continue

        console.print("[red]无效输入。请参考上方操作说明。[/]")


# ---------------------------------------------------------------------------
# 定时任务管理页
# ---------------------------------------------------------------------------

def page_manage_tasks(cfg: AppConfig, config_path: Path) -> None:
    from .tasks import list_tasks, register_tasks, delete_task, delete_all_tasks, run_task_now, _hm_to_task_name

    while True:
        _clear()
        _header("📅 定时任务管理")

        console.print(
            f"配置时间点（auto_snapshot_times）：[bold cyan]{cfg.auto_snapshot_times or '未配置'}[/]\n"
        )

        # 获取系统已注册任务
        try:
            registered = {t["name"]: t for t in list_tasks()}
        except Exception as e:
            registered = {}
            console.print(f"[yellow]查询计划任务失败：{e}[/]")

        # 合并配置时间点与已注册任务，统一展示
        all_times = list(cfg.auto_snapshot_times)
        extra_names = set(registered.keys()) - {_hm_to_task_name(hm) for hm in all_times}
        extra_times = [t["time"] for t in registered.values() if t["name"] in extra_names]
        display_times = all_times + extra_times

        t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold magenta")
        t.add_column("序号", width=5, justify="right")
        t.add_column("时间点", width=8)
        t.add_column("任务名", style="dim")
        t.add_column("状态", width=12)
        t.add_column("下次运行")
        t.add_column("在配置中", width=8, justify="center")

        for i, hm in enumerate(display_times, 1):
            task_name = _hm_to_task_name(hm)
            in_cfg = hm in cfg.auto_snapshot_times
            info = registered.get(task_name)
            if info:
                status_str = f"[green]{info['status']}[/]"
                next_run = info.get("next_run", "N/A")
            else:
                status_str = "[dim]未注册[/]"
                next_run = "-"
            t.add_row(
                str(i),
                hm,
                task_name,
                status_str,
                next_run,
                "✓" if in_cfg else "[yellow]已移除[/]",
            )
        console.print(t)

        console.print(
            "\n[bold]操作说明[/]\n"
            "  [bold cyan][r][/]             → 注册/更新全部任务（以 config.json 为准）\n"
            "  [bold red]d+序号[/]（如 [bold]d1[/]）→ 删除单条任务\n"
            "  [bold red][D][/]             → 删除全部已注册任务\n"
            "  [bold green]t+序号[/]（如 [bold]t1[/]）→ 立即触发该时间点快照\n"
            "  [bold]0[/]               → 返回主菜单\n"
        )

        raw = Prompt.ask("[bold]请输入[/]", default="0").strip().lower()

        if raw == "0":
            return

        # 注册/更新
        if raw == "r":
            if not cfg.auto_snapshot_times:
                console.print("[yellow]config.json 中未配置 auto_snapshot_times，无任务可注册。[/]")
            else:
                try:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        transient=True,
                        console=console,
                    ) as prog:
                        prog.add_task("正在注册计划任务...", total=None)
                        ok = register_tasks(cfg, config_path)
                    console.print(
                        f"[green]✓ 已注册 {len(ok)} 条任务：{', '.join(ok)}[/]"
                    )
                except Exception as e:
                    console.print(f"[red]注册失败：{e}[/]")
            Prompt.ask("\n按 Enter 继续", default="")
            continue

        # 删除全部
        if raw == "d":
            if Confirm.ask("[red]确认删除全部 DailyReporter-* 任务？[/]", default=False):
                n = delete_all_tasks()
                console.print(f"[green]✓ 已删除 {n} 条任务。[/]")
            else:
                console.print("[dim]已取消。[/]")
            Prompt.ask("\n按 Enter 继续", default="")
            continue

        # 删除单条：d<N>
        if raw.startswith("d") and raw[1:].isdigit():
            n = int(raw[1:])
            if 1 <= n <= len(display_times):
                hm = display_times[n - 1]
                task_name = _hm_to_task_name(hm)
                if Confirm.ask(f"[red]确认删除任务 {task_name}？[/]", default=False):
                    ok = delete_task(task_name)
                    console.print(
                        f"[green]✓ 已删除 {task_name}[/]" if ok else f"[red]删除失败（任务可能不存在）[/]"
                    )
                else:
                    console.print("[dim]已取消。[/]")
            else:
                console.print(f"[red]序号超出范围，请输入 1 ~ {len(display_times)}。[/]")
            Prompt.ask("\n按 Enter 继续", default="")
            continue

        # 立即触发：t<N>
        if raw.startswith("t") and raw[1:].isdigit():
            n = int(raw[1:])
            if 1 <= n <= len(display_times):
                hm = display_times[n - 1]
                console.print(f"\n正在立即打快照（时间点 {hm}）...")
                snap = run_task_now(cfg, hm)
                if snap:
                    console.print(
                        f"[green]✓ 快照已保存：{snap['id']}，{snap['file_count']} 个文件[/]"
                    )
                else:
                    console.print("[red]快照失败，请检查配置。[/]")
            else:
                console.print(f"[red]序号超出范围，请输入 1 ~ {len(display_times)}。[/]")
            Prompt.ask("\n按 Enter 继续", default="")
            continue

        console.print("[red]无效输入。请参考上方操作说明。[/]")
        time.sleep(0.8)


# ---------------------------------------------------------------------------
# 主菜单
# ---------------------------------------------------------------------------

def run_interactive(config_path: Path) -> None:
    while True:
        _clear()
        # 每次回主菜单时重新加载配置，使手动编辑立即生效
        cfg = load_config(config_path)
        menu_items = [
            ("1", "📸 打快照",              lambda: page_take_snapshot(cfg)),
            ("2", "📋 浏览/管理快照",        lambda: page_browse_snapshots(cfg)),
            ("3", "🔍 对比快照",             lambda: page_compare_snapshots(cfg)),
            ("4", "📄 生成日报",              lambda: page_generate_report(cfg)),
            ("5", "📑 日报管理",              lambda: page_manage_reports(cfg)),
            ("6", "⏱  Watch（定时快照）",    lambda: page_watch(cfg)),
            ("7", "⚙️  查看配置",             lambda: page_view_config(cfg, config_path)),
            ("8", "📅 定时任务管理",          lambda: page_manage_tasks(cfg, config_path)),
            ("0", "🚪 退出",                 None),
        ]

        console.print(Panel(
            "[bold cyan]Kgent V3  ·  文件变更监控 · AI 日报生成[/]\n"
            f"[dim]配置：{config_path}[/]",
            border_style="cyan",
            padding=(1, 4),
        ))

        index = load_index(cfg)
        reports = list_reports(cfg)
        console.print(
            f"[dim]快照总数：{len(index)}  |  "
            f"日报总数：{len(reports)}  |  "
            f"监控目录：{len(cfg.watch_paths)} 个  |  "
            f"自动快照：{cfg.auto_snapshot_times or '未配置'}[/]\n"
        )

        for key, label, _ in menu_items:
            console.print(f"  [bold cyan]{key}[/]  {label}")

        console.print()
        choice = Prompt.ask("[bold]请选择[/]", default="0").strip()

        matched = [(k, lbl, fn) for k, lbl, fn in menu_items if k == choice]
        if not matched:
            console.print("[red]无效选项，请重新输入。[/]")
            time.sleep(1)
            continue

        key, label, fn = matched[0]
        if fn is None:
            console.print("\n[dim]再见！[/]")
            break

        fn()
