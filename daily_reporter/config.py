# -*- coding: utf-8 -*-
"""配置加载模块"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set


@dataclass
class AppConfig:
    watch_paths: List[Path]
    ignore_dirs: Set[str] = field(default_factory=set)
    ignore_suffixes: Set[str] = field(default_factory=set)
    ignore_patterns: List[str] = field(default_factory=list)
    snapshot_root: Path = field(default_factory=lambda: Path(".daily_reporter"))
    output_root: Path = field(default_factory=lambda: Path("reports"))
    encoding: str = "utf-8"
    auto_snapshot_times: List[str] = field(default_factory=list)
    max_file_size_kb: int = 1024
    # AI 总结配置（可选，ai_provider="disabled" 时完全不加载 AI 库）
    ai_provider: str = "disabled"   # disabled | zhipuai | openai | ollama
    ai_model: str = ""
    ai_api_key: str = ""
    ai_base_url: str = ""           # openai-compatible 或 ollama 地址
    ai_prompt_template: Path = field(default_factory=lambda: Path(""))  # 自定义报告生成 prompt 模板路径


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
        ai_provider=str(raw.get("ai_provider", "disabled")),
        ai_model=str(raw.get("ai_model", "")),
        ai_api_key=str(raw.get("ai_api_key", "")),
        ai_base_url=str(raw.get("ai_base_url", "")),
        ai_prompt_template=(
            (config_path.parent / raw["ai_prompt_template"]).resolve()
            if raw.get("ai_prompt_template")
            else Path("")
        ),
    )
