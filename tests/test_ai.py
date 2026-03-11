# -*- coding: utf-8 -*-
"""Unit tests for daily_reporter.ai"""

import sys
import types
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from daily_reporter.config import AppConfig
from daily_reporter.ai import (
    build_prompt,
    build_report_prompt,
    get_provider,
    OllamaProvider,
    ZhipuAIProvider,
    OpenAIProvider,
    append_ai_summary,
    _DEFAULT_REPORT_TEMPLATE,
    _MAX_PROMPT_CHARS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _cfg(provider: str = "disabled", model: str = "", api_key: str = "",
         base_url: str = "", tpl: Path = Path("")) -> AppConfig:
    return AppConfig(
        watch_paths=[Path(".")],
        ai_provider=provider,
        ai_model=model,
        ai_api_key=api_key,
        ai_base_url=base_url,
        ai_prompt_template=tpl,
    )


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_contains_report_text(self):
        result = build_prompt("some report content")
        assert "some report content" in result

    def test_contains_instructions(self):
        result = build_prompt("report")
        assert "工作总结" in result or "第一人称" in result

    def test_truncates_long_input(self):
        long_text = "x" * (_MAX_PROMPT_CHARS + 5000)
        result = build_prompt(long_text)
        assert "截断" in result or len(result) < len(long_text) + 500

    def test_short_input_not_truncated(self):
        text = "short report"
        result = build_prompt(text)
        assert text in result
        assert "截断" not in result


# ---------------------------------------------------------------------------
# build_report_prompt
# ---------------------------------------------------------------------------

class TestBuildReportPrompt:
    def test_substitutes_placeholder(self):
        template = "Here is the data: {{report_data}}"
        result = build_report_prompt(template, "some data")
        assert "{{report_data}}" not in result
        assert "some data" in result

    def test_placeholder_replaced_exactly_once(self):
        template = "{{report_data}} and again {{report_data}}"
        result = build_report_prompt(template, "DATA")
        # replace() in Python replaces all occurrences
        assert "{{report_data}}" not in result
        assert result.count("DATA") == 2  # Both replaced

    def test_truncates_long_raw_data(self):
        template = "{{report_data}}"
        long_data = "y" * (_MAX_PROMPT_CHARS + 3000)
        result = build_report_prompt(template, long_data)
        assert "截断" in result or len(result) <= _MAX_PROMPT_CHARS + 200

    def test_default_template_has_placeholder(self):
        assert "{{report_data}}" in _DEFAULT_REPORT_TEMPLATE

    def test_empty_template_returns_empty(self):
        result = build_report_prompt("", "data")
        assert result == ""


# ---------------------------------------------------------------------------
# get_provider — factory
# ---------------------------------------------------------------------------

class TestGetProvider:
    def test_unknown_provider_raises_value_error(self):
        cfg = _cfg("unknown_provider")
        with pytest.raises(ValueError, match="未知的 ai_provider"):
            get_provider(cfg)

    def test_ollama_provider_instantiated(self):
        cfg = _cfg("ollama", model="llama3")
        provider = get_provider(cfg)
        assert isinstance(provider, OllamaProvider)

    def test_zhipuai_provider_raises_without_sdk(self, monkeypatch):
        """ZhipuAIProvider should raise RuntimeError if zhipuai not installed."""
        monkeypatch.setitem(sys.modules, "zhipuai", None)  # simulate ImportError
        with pytest.raises((RuntimeError, ImportError)):
            ZhipuAIProvider(api_key="test", model="glm-4")

    def test_openai_provider_raises_without_sdk(self, monkeypatch):
        """OpenAIProvider should raise RuntimeError if openai not installed."""
        monkeypatch.setitem(sys.modules, "openai", None)
        with pytest.raises((RuntimeError, ImportError)):
            OpenAIProvider(api_key="test", model="gpt-4o")

    def test_get_provider_zhipuai_uses_base_url(self, monkeypatch):
        """get_provider should pass base_url to ZhipuAIProvider."""
        mock_zhipuai = types.ModuleType("zhipuai")
        mock_client = MagicMock()
        mock_zhipuai.ZhipuAI = MagicMock(return_value=mock_client)
        monkeypatch.setitem(sys.modules, "zhipuai", mock_zhipuai)

        cfg = _cfg("zhipuai", model="glm-4", api_key="key", base_url="https://custom.api/v4")
        provider = get_provider(cfg)
        assert isinstance(provider, ZhipuAIProvider)
        # Verify base_url was passed to the constructor
        mock_zhipuai.ZhipuAI.assert_called_once()
        call_kwargs = mock_zhipuai.ZhipuAI.call_args
        assert call_kwargs.kwargs.get("base_url") == "https://custom.api/v4"


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------

class TestOllamaProvider:
    def test_default_base_url(self):
        p = OllamaProvider(model="llama3")
        assert "11434" in p._base_url

    def test_custom_base_url(self):
        p = OllamaProvider(model="qwen2.5:7b", base_url="http://192.168.1.100:11434")
        assert "192.168.1.100" in p._base_url

    def test_default_model_fallback(self):
        p = OllamaProvider(model="")
        assert p._model == "qwen2.5:7b"

    def test_custom_model(self):
        p = OllamaProvider(model="mistral:7b")
        assert p._model == "mistral:7b"

    def test_summarize_sends_post(self):
        """summarize() should call urlopen with a JSON body."""
        p = OllamaProvider(model="llama3")
        fake_resp_data = b'{"message": {"content": "summary result"}}'

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_cm = MagicMock()
            mock_cm.__enter__ = MagicMock(return_value=mock_cm)
            mock_cm.__exit__ = MagicMock(return_value=False)
            mock_cm.read = MagicMock(return_value=fake_resp_data)
            mock_urlopen.return_value = mock_cm

            result = p.summarize("test prompt")
            assert result == "summary result"
            mock_urlopen.assert_called_once()


# ---------------------------------------------------------------------------
# append_ai_summary
# ---------------------------------------------------------------------------

class TestAppendAiSummary:
    def test_appends_to_existing_report(self, tmp_path: Path):
        report_file = tmp_path / "report.md"
        report_file.write_text("# Original Report\n", encoding="utf-8")
        append_ai_summary(report_file, "Great work today!", provider_name="zhipuai")
        content = report_file.read_text(encoding="utf-8")
        assert "# Original Report" in content
        assert "Great work today!" in content

    def test_creates_chapter_nine(self, tmp_path: Path):
        report_file = tmp_path / "report.md"
        report_file.write_text("# Report\n", encoding="utf-8")
        append_ai_summary(report_file, "Summary text")
        content = report_file.read_text(encoding="utf-8")
        assert "## 九、AI 智能总结" in content

    def test_includes_provider_name(self, tmp_path: Path):
        report_file = tmp_path / "report.md"
        report_file.write_text("# Report\n", encoding="utf-8")
        append_ai_summary(report_file, "text", provider_name="openai")
        content = report_file.read_text(encoding="utf-8")
        assert "openai" in content

    def test_no_provider_name_no_parentheses(self, tmp_path: Path):
        report_file = tmp_path / "report.md"
        report_file.write_text("# Report\n", encoding="utf-8")
        append_ai_summary(report_file, "summary", provider_name="")
        content = report_file.read_text(encoding="utf-8")
        # Should not contain empty parens like "()"
        assert "()" not in content

    def test_original_content_preserved(self, tmp_path: Path):
        report_file = tmp_path / "report.md"
        original = "# Existing Content\n\nSome text here.\n"
        report_file.write_text(original, encoding="utf-8")
        append_ai_summary(report_file, "AI stuff")
        content = report_file.read_text(encoding="utf-8")
        assert "Some text here." in content
