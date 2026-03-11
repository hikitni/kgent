# -*- coding: utf-8 -*-
"""配置查看 API 路由"""

from fastapi import APIRouter

from ..deps import get_config as _get_config

router = APIRouter()


@router.get("")
async def get_config():
    cfg = _get_config()
    return {
        "ok": True,
        "watch_paths": [str(p) for p in cfg.watch_paths],
        "snapshot_root": str(cfg.snapshot_root),
        "output_root": str(cfg.output_root),
        "encoding": cfg.encoding,
        "max_file_size_kb": cfg.max_file_size_kb,
        "auto_snapshot_times": cfg.auto_snapshot_times,
        "ignore_dirs": sorted(cfg.ignore_dirs),
        "ignore_suffixes": sorted(cfg.ignore_suffixes),
        "ignore_patterns": cfg.ignore_patterns,
        "ai_provider": cfg.ai_provider,
        "ai_model": cfg.ai_model,
        "ai_api_key": "***" if cfg.ai_api_key else "",   # 脱敏
        "ai_base_url": cfg.ai_base_url,
    }
