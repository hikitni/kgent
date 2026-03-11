# -*- coding: utf-8 -*-
"""快照采集与管理模块"""

import datetime as dt
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .config import AppConfig

logger = logging.getLogger("daily_reporter.snapshot")


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _snap_id(ts: dt.datetime) -> str:
    return ts.strftime("%Y%m%d-%H%M%S")


def _snap_filename(snap_id: str) -> str:
    return f"snapshot-{snap_id}.json"


def _snap_content_filename(snap_id: str) -> str:
    """文件内容分离存储的文件名。"""
    return f"snapshot-{snap_id}.content.json"


def index_path(cfg: AppConfig) -> Path:
    return cfg.snapshot_root / "index.json"


def snapshots_dir(cfg: AppConfig) -> Path:
    return cfg.snapshot_root / "snapshots"


def should_ignore(path: Path, cfg: AppConfig) -> bool:
    if any(part in cfg.ignore_dirs for part in path.parts):
        return True
    if path.suffix.lower() in cfg.ignore_suffixes:
        return True
    for pat in cfg.ignore_patterns:
        if re.search(pat, str(path)):
            return True
    return False


def _read_file_content(path: Path, cfg: AppConfig) -> Tuple[Optional[List[str]], str]:
    """返回 (行列表 | None, MD5)。大文件 lines=None 只存哈希。"""
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
    except Exception as exc:
        logger.warning("读取文件失败 %s: %s", path, exc)
        return None, ""


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def load_index(cfg: AppConfig) -> List[dict]:
    idx = index_path(cfg)
    if not idx.exists():
        return []
    with idx.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_index(cfg: AppConfig, index: List[dict]) -> None:
    index_path(cfg).parent.mkdir(parents=True, exist_ok=True)
    with index_path(cfg).open("w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def take_snapshot(cfg: AppConfig, label: str = "manual", trigger: str = "manual") -> dict:
    """扫描监控目录，生成并保存快照（元数据 + 内容分离），返回快照元数据。"""
    now = dt.datetime.now()
    snap_id = _snap_id(now)

    files_meta = {}   # path -> {"hash": ...}
    files_content = {}  # path -> [lines]  (仅非大文件)
    scanned = skipped = 0
    for watch_path in cfg.watch_paths:
        if not watch_path.exists():
            continue
        for p in watch_path.rglob("*"):
            if not p.is_file():
                continue
            if should_ignore(p, cfg):
                skipped += 1
                continue
            lines, md5 = _read_file_content(p, cfg)
            files_meta[str(p)] = {"hash": md5}
            if lines is not None:
                files_content[str(p)] = lines
            scanned += 1

    # 元数据文件（轻量，用于列表/判断变更）
    snapshot_meta = {
        "id": snap_id,
        "timestamp": now.isoformat(timespec="seconds"),
        "label": label,
        "trigger": trigger,
        "file_count": scanned,
        "skipped_count": skipped,
        "files": files_meta,
    }

    sdir = snapshots_dir(cfg)
    sdir.mkdir(parents=True, exist_ok=True)

    with (sdir / _snap_filename(snap_id)).open("w", encoding="utf-8") as f:
        json.dump(snapshot_meta, f, ensure_ascii=False)

    # 内容文件（按需加载，仅 diff 时需要）
    with (sdir / _snap_content_filename(snap_id)).open("w", encoding="utf-8") as f:
        json.dump(files_content, f, ensure_ascii=False)

    idx = load_index(cfg)
    idx.append({
        "id": snap_id,
        "timestamp": now.isoformat(timespec="seconds"),
        "label": label,
        "trigger": trigger,
        "file_count": scanned,
    })
    save_index(cfg, idx)

    # 返回完整快照（包含 lines），兼容调用方
    full_files = {}
    for path, meta in files_meta.items():
        full_files[path] = {
            "hash": meta["hash"],
            "lines": files_content.get(path),
        }
    snapshot_meta["files"] = full_files
    return snapshot_meta


def load_snapshot_meta(cfg: AppConfig, snap_id: str) -> dict:
    """仅加载快照元数据（不含文件内容行），用于列表展示等轻量场景。"""
    snap_file = snapshots_dir(cfg) / _snap_filename(snap_id)
    if not snap_file.exists():
        raise FileNotFoundError(f"快照不存在: {snap_id}")
    with snap_file.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_snapshot(cfg: AppConfig, snap_id: str) -> dict:
    """加载完整快照（元数据 + 文件内容），兼容新旧两种格式。"""
    meta = load_snapshot_meta(cfg, snap_id)

    # 尝试读取分离的 content 文件
    content_file = snapshots_dir(cfg) / _snap_content_filename(snap_id)
    if content_file.exists():
        with content_file.open("r", encoding="utf-8") as f:
            content = json.load(f)
        # 合并 content 到 meta.files
        for path, file_meta in meta.get("files", {}).items():
            if "lines" not in file_meta:
                file_meta["lines"] = content.get(path)
    else:
        # 旧格式兼容：files 中已包含 lines
        pass

    return meta


def delete_snapshot(cfg: AppConfig, snap_id: str) -> bool:
    """删除快照文件（含 content 文件）并从索引移除，返回是否成功。"""
    sdir = snapshots_dir(cfg)
    snap_file = sdir / _snap_filename(snap_id)
    content_file = sdir / _snap_content_filename(snap_id)
    removed_file = False
    if snap_file.exists():
        snap_file.unlink()
        removed_file = True
    if content_file.exists():
        content_file.unlink()
        removed_file = True

    idx = load_index(cfg)
    new_idx = [s for s in idx if s["id"] != snap_id]
    if len(new_idx) != len(idx):
        save_index(cfg, new_idx)
        return True
    return removed_file
