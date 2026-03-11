# -*- coding: utf-8 -*-
"""Unit tests for daily_reporter.config"""

import json
import pytest
from pathlib import Path

from daily_reporter.config import AppConfig, load_config


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_config(tmp_path: Path, data: dict) -> Path:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return cfg_file


# ---------------------------------------------------------------------------
# AppConfig dataclass defaults
# ---------------------------------------------------------------------------

class TestAppConfigDefaults:
    def test_default_snapshot_root(self):
        cfg = AppConfig(watch_paths=[Path(".")])
        assert cfg.snapshot_root == Path(".daily_reporter")

    def test_default_output_root(self):
        cfg = AppConfig(watch_paths=[Path(".")])
        assert cfg.output_root == Path("reports")

    def test_default_ai_provider_disabled(self):
        cfg = AppConfig(watch_paths=[Path(".")])
        assert cfg.ai_provider == "disabled"

    def test_default_max_file_size(self):
        cfg = AppConfig(watch_paths=[Path(".")])
        assert cfg.max_file_size_kb == 1024

    def test_default_ignore_dirs_empty_set(self):
        cfg = AppConfig(watch_paths=[Path(".")])
        assert isinstance(cfg.ignore_dirs, set)
        assert len(cfg.ignore_dirs) == 0


# ---------------------------------------------------------------------------
# load_config — happy path
# ---------------------------------------------------------------------------

class TestLoadConfigSuccess:
    def test_watch_paths_resolved(self, tmp_path: Path):
        data = {"watch_paths": [str(tmp_path)]}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert len(cfg.watch_paths) == 1
        assert cfg.watch_paths[0].is_absolute()

    def test_multiple_watch_paths(self, tmp_path: Path):
        p1 = tmp_path / "a"
        p2 = tmp_path / "b"
        p1.mkdir(); p2.mkdir()
        data = {"watch_paths": [str(p1), str(p2)]}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert len(cfg.watch_paths) == 2

    def test_ignore_dirs_as_set(self, tmp_path: Path):
        data = {"watch_paths": [str(tmp_path)], "ignore_dirs": [".git", "node_modules"]}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert isinstance(cfg.ignore_dirs, set)
        assert ".git" in cfg.ignore_dirs
        assert "node_modules" in cfg.ignore_dirs

    def test_ignore_suffixes_as_set(self, tmp_path: Path):
        data = {"watch_paths": [str(tmp_path)], "ignore_suffixes": [".log", ".tmp"]}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert ".log" in cfg.ignore_suffixes

    def test_max_file_size_kb(self, tmp_path: Path):
        data = {"watch_paths": [str(tmp_path)], "max_file_size_kb": 512}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert cfg.max_file_size_kb == 512

    def test_ai_provider_field(self, tmp_path: Path):
        data = {"watch_paths": [str(tmp_path)], "ai_provider": "ollama", "ai_model": "llama3"}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert cfg.ai_provider == "ollama"
        assert cfg.ai_model == "llama3"

    def test_auto_snapshot_times(self, tmp_path: Path):
        data = {"watch_paths": [str(tmp_path)], "auto_snapshot_times": ["06:00", "18:00"]}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert cfg.auto_snapshot_times == ["06:00", "18:00"]

    def test_snapshot_root_resolved(self, tmp_path: Path):
        data = {"watch_paths": [str(tmp_path)], "snapshot_root": ".daily_reporter"}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert cfg.snapshot_root.is_absolute()

    def test_ai_prompt_template_resolved(self, tmp_path: Path):
        """ai_prompt_template is resolved relative to the config file's directory."""
        tpl = tmp_path / "my_prompt.md"
        tpl.write_text("hello {{report_data}}", encoding="utf-8")
        data = {"watch_paths": [str(tmp_path)], "ai_prompt_template": "my_prompt.md"}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert cfg.ai_prompt_template.name == "my_prompt.md"
        assert cfg.ai_prompt_template.is_absolute()

    def test_ai_prompt_template_empty_when_not_set(self, tmp_path: Path):
        data = {"watch_paths": [str(tmp_path)]}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        # Path("") serializes as "." on some platforms; both represent "not set"
        assert cfg.ai_prompt_template == Path("")

    def test_encoding_default_utf8(self, tmp_path: Path):
        data = {"watch_paths": [str(tmp_path)]}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert cfg.encoding == "utf-8"

    def test_custom_encoding(self, tmp_path: Path):
        data = {"watch_paths": [str(tmp_path)], "encoding": "gbk"}
        cfg_file = _write_config(tmp_path, data)
        cfg = load_config(cfg_file)
        assert cfg.encoding == "gbk"


# ---------------------------------------------------------------------------
# load_config — error cases
# ---------------------------------------------------------------------------

class TestLoadConfigErrors:
    def test_missing_file_raises_system_exit(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.json"
        with pytest.raises(SystemExit):
            load_config(missing)

    def test_empty_watch_paths_raises_system_exit(self, tmp_path: Path):
        data = {"watch_paths": []}
        cfg_file = _write_config(tmp_path, data)
        with pytest.raises(SystemExit):
            load_config(cfg_file)

    def test_missing_watch_paths_key_raises_system_exit(self, tmp_path: Path):
        data = {}
        cfg_file = _write_config(tmp_path, data)
        with pytest.raises(SystemExit):
            load_config(cfg_file)
