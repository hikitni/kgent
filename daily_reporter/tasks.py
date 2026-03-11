# -*- coding: utf-8 -*-
"""
Windows 计划任务管理（封装 schtasks.exe）

任务命名规则：DailyReporter-HHMM（如 DailyReporter-0600）
每条任务每天在指定时间调用：
    python <main.py 绝对路径> snapshot --config <config.json 绝对路径> --label <auto>
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .config import AppConfig
from .snapshot import take_snapshot
from .utils import hm_to_label

# 任务名前缀，用于识别本程序注册的任务
_TASK_PREFIX = "DailyReporter-"


def _hm_to_task_name(hm: str) -> str:
    """'06:00' → 'DailyReporter-0600'"""
    return _TASK_PREFIX + hm.replace(":", "")


def _run_schtasks(*args: str) -> subprocess.CompletedProcess:
    """运行 schtasks.exe，返回 CompletedProcess（stdout/stderr 均为文本）。"""
    return subprocess.run(
        ["schtasks", *args],
        capture_output=True,
        text=True,
        encoding="gbk",   # schtasks 在中文 Windows 上输出 GBK
        errors="replace",
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def list_tasks() -> List[dict]:
    """
    查询所有 DailyReporter-* 计划任务。

    返回列表，每项：
        {
            "name": "DailyReporter-0600",
            "time": "06:00",
            "next_run": "2026/03/05 06:00:00",   # 或 "N/A"
            "status": "就绪" / "正在运行" / "已禁用" / "未知",
            "registered": True,
        }
    """
    result = _run_schtasks("/Query", "/FO", "LIST", "/V")
    tasks = []

    current: dict = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        # 任务名行（不同 Windows 版本格式略有差异）
        if line.startswith("任务名:") or line.startswith("TaskName:"):
            name = line.split(":", 1)[1].strip().lstrip("\\")
            if name.startswith(_TASK_PREFIX):
                current = {"name": name, "registered": True}
                tasks.append(current)
        elif current:
            if line.startswith("下次运行时间:") or line.startswith("Next Run Time:"):
                current["next_run"] = line.split(":", 1)[1].strip()
            elif line.startswith("状态:") or line.startswith("Status:"):
                current["status"] = line.split(":", 1)[1].strip()

    # 解析 time 字段（从任务名反推）
    for t in tasks:
        raw = t["name"][len(_TASK_PREFIX):]   # "0600"
        if len(raw) == 4 and raw.isdigit():
            t["time"] = f"{raw[:2]}:{raw[2:]}"
        else:
            t["time"] = "?"
        t.setdefault("next_run", "N/A")
        t.setdefault("status", "未知")

    return tasks


def registered_task_names() -> List[str]:
    """返回已注册的 DailyReporter-* 任务名列表（快速查询，不含详细信息）。"""
    result = _run_schtasks("/Query", "/FO", "CSV", "/NH")
    names = []
    for line in result.stdout.splitlines():
        # CSV 第一列是任务名，带引号，如 "\"\\DailyReporter-0600\""
        m = re.match(r'^"?\\?([^"\\,]+)"?', line)
        if m and m.group(1).startswith(_TASK_PREFIX):
            names.append(m.group(1))
    return names


def register_tasks(cfg: AppConfig, config_path: Path) -> List[str]:
    """
    将 cfg.auto_snapshot_times 同步为系统计划任务：
    - 创建/覆盖配置中存在的时间点对应任务
    - 删除配置中已移除的旧任务（仅操作 DailyReporter-* 前缀的任务）

    返回已注册成功的任务名列表。
    """
    main_py = _find_main_py()
    python_exe = sys.executable            # 当前运行的 python.exe 路径
    config_abs = str(config_path.resolve())

    new_names = {_hm_to_task_name(hm) for hm in cfg.auto_snapshot_times}
    old_names = set(registered_task_names())

    # 删除多余旧任务
    for name in old_names - new_names:
        _run_schtasks("/Delete", "/TN", name, "/F")

    registered = []
    for hm in cfg.auto_snapshot_times:
        task_name = _hm_to_task_name(hm)
        label = hm_to_label(hm)
        cmd = (
            f'"{python_exe}" "{main_py}" '
            f'--config "{config_abs}" snapshot --label {label}'
        )
        result = _run_schtasks(
            "/Create",
            "/F",                       # 已存在则覆盖
            "/SC", "DAILY",
            "/ST", hm,
            "/TN", task_name,
            "/TR", cmd,
            "/RU", "",                  # 以当前登录用户运行（无需密码）
        )
        if result.returncode == 0:
            registered.append(task_name)

    return registered


def delete_task(task_name: str) -> bool:
    """删除指定任务，返回是否成功。"""
    result = _run_schtasks("/Delete", "/TN", task_name, "/F")
    return result.returncode == 0


def delete_all_tasks() -> int:
    """删除全部 DailyReporter-* 任务，返回实际删除数量。"""
    names = registered_task_names()
    count = 0
    for name in names:
        if delete_task(name):
            count += 1
    return count


def run_task_now(cfg: AppConfig, hm: str) -> Optional[dict]:
    """
    立即触发指定时间点的快照（不经过 schtasks，直接调用 take_snapshot）。
    返回快照 dict，失败时返回 None。
    """
    label = hm_to_label(hm)
    try:
        return take_snapshot(cfg, label=label, trigger="manual")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _find_main_py() -> str:
    """找到 main.py 的绝对路径。"""
    # main.py 总是在 daily_reporter 包的上一级
    here = Path(__file__).resolve().parent.parent
    return str(here / "main.py")


# _hm_to_label 已迁移至 daily_reporter.utils.hm_to_label
_hm_to_label = hm_to_label
