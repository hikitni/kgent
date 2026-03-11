# -*- coding: utf-8 -*-
"""共享依赖：配置路径状态与带 TTL 的配置缓存，供路由模块导入。"""

import time
from pathlib import Path

from daily_reporter.config import AppConfig, load_config

_config_path: Path = Path("config.json")

# 缓存：(AppConfig, 上次加载时间戳)
_cached_config: AppConfig | None = None
_cached_ts: float = 0.0
_CACHE_TTL: float = 5.0  # 秒


def set_config_path(p: Path) -> None:
    global _config_path, _cached_config, _cached_ts
    _config_path = p
    _cached_config = None
    _cached_ts = 0.0


def get_config_path() -> Path:
    return _config_path


def get_config() -> AppConfig:
    """带 TTL 的配置缓存，5 秒内多次调用只读取一次磁盘。"""
    global _cached_config, _cached_ts
    now = time.monotonic()
    if _cached_config is not None and (now - _cached_ts) < _CACHE_TTL:
        return _cached_config
    _cached_config = load_config(_config_path)
    _cached_ts = now
    return _cached_config


def invalidate_config_cache() -> None:
    """手动失效缓存（配置变更后调用）。"""
    global _cached_config, _cached_ts
    _cached_config = None
    _cached_ts = 0.0
