# -*- coding: utf-8 -*-
"""公共工具函数 — 消除跨模块重复代码"""

import logging
import math
import re
from typing import List, Tuple

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logger = logging.getLogger("daily_reporter")


def setup_logging(level: int = logging.INFO) -> None:
    """统一初始化日志格式（仅需在入口调用一次）。"""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)-5s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    root = logging.getLogger("daily_reporter")
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(level)


# ---------------------------------------------------------------------------
# 时间标签（由 ui.py / tasks.py / watch.py 共用）
# ---------------------------------------------------------------------------

def hm_to_label(hm: str) -> str:
    """将 HH:MM 时间转换为英文标签 (morning/noon/afternoon/evening)。"""
    h = int(hm.split(":")[0])
    if 5 <= h < 10:
        return "morning"
    if 10 <= h < 14:
        return "noon"
    if 14 <= h < 19:
        return "afternoon"
    return "evening"


# ---------------------------------------------------------------------------
# 快照 ID 正则（由 snapshots.py / compare.py 共用）
# ---------------------------------------------------------------------------

SNAP_ID_RE = re.compile(r"^\d{8}-\d{6}$")


# ---------------------------------------------------------------------------
# 分页辅助（由 ui.py 共用）
# ---------------------------------------------------------------------------

def paginate(items: list, page: int, page_size: int = 20) -> Tuple[list, int, int]:
    """将列表分页，返回 (当前页数据, 总页数, 实际页码)。"""
    total_pages = max(1, math.ceil(len(items) / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    return items[start : start + page_size], total_pages, page
