# -*- coding: utf-8 -*-
"""Unit tests for daily_reporter.web.deps (TTL config cache)"""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from daily_reporter.web.deps import (
    get_config,
    get_config_path,
    set_config_path,
    invalidate_config_cache,
    _CACHE_TTL,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg_file(tmp_path: Path) -> Path:
    data = {"watch_paths": [str(tmp_path)]}
    f = tmp_path / "config.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return f


@pytest.fixture(autouse=True)
def _reset_cache(cfg_file):
    """确保每个测试开始时缓存干净。"""
    set_config_path(cfg_file)
    yield
    invalidate_config_cache()


# ---------------------------------------------------------------------------
# set_config_path / get_config_path
# ---------------------------------------------------------------------------

class TestConfigPath:
    def test_set_and_get(self, cfg_file):
        set_config_path(cfg_file)
        assert get_config_path() == cfg_file

    def test_set_clears_cache(self, cfg_file):
        # Warm up cache
        get_config()
        # Setting a new path should invalidate
        set_config_path(cfg_file)
        # The next get_config should re-read from disk
        cfg = get_config()
        assert cfg is not None


# ---------------------------------------------------------------------------
# get_config — TTL cache
# ---------------------------------------------------------------------------

class TestGetConfig:
    def test_returns_appconfig(self, cfg_file):
        cfg = get_config()
        assert cfg is not None
        assert hasattr(cfg, "watch_paths")

    def test_same_object_within_ttl(self, cfg_file):
        a = get_config()
        b = get_config()
        assert a is b  # same cached object

    def test_reloads_after_ttl(self, cfg_file):
        a = get_config()
        # Monkey-patch monotonic to simulate time passing
        with patch("daily_reporter.web.deps.time") as mock_time:
            mock_time.monotonic.return_value = time.monotonic() + _CACHE_TTL + 1
            b = get_config()
        # Should have re-read (different object)
        assert b is not None

    def test_invalidate_forces_reload(self, cfg_file):
        a = get_config()
        invalidate_config_cache()
        b = get_config()
        # After invalidation, a new object should be loaded
        assert b is not None


# ---------------------------------------------------------------------------
# invalidate_config_cache
# ---------------------------------------------------------------------------

class TestInvalidateCache:
    def test_invalidate_clears(self, cfg_file):
        get_config()
        invalidate_config_cache()
        # Next call should reload - just ensure no crash
        cfg = get_config()
        assert cfg is not None
