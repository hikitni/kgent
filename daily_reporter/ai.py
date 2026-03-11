# -*- coding: utf-8 -*-
"""
AI 总结模块 — 多 Provider 支持
支持: zhipuai | openai（及兼容接口：DeepSeek/Moonshot/...） | ollama（本地，纯 HTTP）

接入方式：在 config.json 中配置以下字段
  ai_provider : "disabled" | "zhipuai" | "openai" | "ollama"
  ai_model    : 模型名称，如 "glm-4" / "gpt-4o" / "qwen2.5:7b"
  ai_api_key  : API Key（ollama 本地无需填写）
  ai_base_url : 自定义 endpoint（openai-compatible 或 ollama 地址）
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import AppConfig

# 发送给 AI 的最大 prompt 字符数（避免超出 context window）
_MAX_PROMPT_CHARS = 20_000
# AI 生成内容的最大 token 数
_MAX_TOKENS = 2000

# 内置默认报告生成 prompt（未配置模板文件时使用）
_DEFAULT_REPORT_TEMPLATE = """\
你是一位专业的软件工程技术项目管理助手。以下是今日工作日报的原始变更数据。请根据这些信息生成一份完整的、专业的中文工作日报。

将零散的文件变更整合为有意义的工作事项，用第一人称，语言专业简洁。
严格按照如下 Markdown 格式输出，不要输出任何额外说明或解释：

# 工作日报

- **日期**：[根据快照时间推断]
- **起止时间**：[快照起点时间] → [快照终点时间]
- **生成方式**：AI 智能生成

---

## 一、今日工作概述

[2-4 句话，高度概括今日工作方向和主要成果]

## 二、工作详情

[按模块/功能方向分条列举，每条以 `- ` 开头]

## 三、关键代码变更说明

[挪选最重要的 3-5 处改动，每条以 `- **文件名**：` 开头]

## 四、问题与风险

[列举开发中遇到的问题或潜在风险；若无则填写“暂无发现明显问题”，每条以 `- ` 开头]

## 五、明日计划

[基于当前进度，给出 3-5 条具体可执行的下一步计划，每条以 `- ` 开头]

---

**以下是原始变更数据，请据此生成上方日报：**

{{report_data}}
"""


# ---------------------------------------------------------------------------
# Prompt 构建
# ---------------------------------------------------------------------------

def build_prompt(report_text: str) -> str:
    """将日报文本裁剪后构建统一 prompt（用于追加型总结）。"""
    body = report_text[:_MAX_PROMPT_CHARS]
    if len(report_text) > _MAX_PROMPT_CHARS:
        body += "\n\n...(内容已截断，仅展示前部分)"

    return (
        "你是一位专业的技术项目管理助手。以下是今日工作日报的原始数据，"
        "请根据这些信息生成一份简洁、专业的工作总结，要求：\n"
        "1. 用第一人称描述今日完成的工作内容\n"
        "2. 分析主要工作方向和技术成果\n"
        "3. 指出需要关注的风险或问题（若有）\n"
        "4. 给出明日改进建议\n"
        "5. 语言简洁专业，控制在 300 字以内\n\n"
        "--- 日报原始数据 ---\n"
        f"{body}\n"
        "--- 结束 ---\n\n"
        "请直接输出总结内容，不要重复原始数据。"
    )


def build_report_prompt(template: str, raw_data: str) -> str:
    """用模板 + 原始数据构建全文重写 prompt。"""
    data_body = raw_data[:_MAX_PROMPT_CHARS]
    if len(raw_data) > _MAX_PROMPT_CHARS:
        data_body += "\n\n...(内容已截断，仅展示前部分)"
    return template.replace("{{report_data}}", data_body)


# ---------------------------------------------------------------------------
# Provider 抽象基类
# ---------------------------------------------------------------------------

class BaseProvider(ABC):
    @abstractmethod
    def summarize(self, prompt: str) -> str:
        """发送 prompt，返回 AI 回复文本。"""
        ...


# ---------------------------------------------------------------------------
# 智谱 GLM Provider
# ---------------------------------------------------------------------------

class ZhipuAIProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, base_url: str = ""):
        try:
            from zhipuai import ZhipuAI  # type: ignore
        except ImportError as _e:
            raise RuntimeError(
                f"无法加载 zhipuai（{_e}）\n"
                "请执行: pip install zhipuai\n"
                "Python 3.14+ 还需执行: pip install sniffio\n"
                "或将 ai_provider 改为其他选项。"
            )
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = ZhipuAI(**kwargs)
        self._model = model or "glm-4"

    def summarize(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=_MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# OpenAI / 兼容接口 Provider（DeepSeek、Moonshot/Kimi 等）
# ---------------------------------------------------------------------------

class OpenAIProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, base_url: str = ""):
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            raise RuntimeError(
                "未安装 openai，请执行: pip install openai\n"
                "此 Provider 同时支持 OpenAI / DeepSeek / Moonshot 等兼容接口。"
            )
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)  # type: ignore[arg-type]
        self._model = model or "gpt-4o"

    def summarize(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=_MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Ollama 本地 Provider（纯 HTTP，无需额外依赖）
# ---------------------------------------------------------------------------

class OllamaProvider(BaseProvider):
    def __init__(self, model: str, base_url: str = ""):
        self._model = model or "qwen2.5:7b"
        self._base_url = (base_url or "http://localhost:11434").rstrip("/")

    def summarize(self, prompt: str) -> str:
        url = f"{self._base_url}/api/chat"
        payload = json.dumps({
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": _MAX_TOKENS},
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"无法连接 Ollama 服务（{self._base_url}）：{e}\n"
                "请确认 Ollama 已启动：ollama serve"
            )

        # Ollama /api/chat 返回 {"message": {"content": "..."}}
        return data.get("message", {}).get("content", "").strip()


# ---------------------------------------------------------------------------
# Provider 工厂
# ---------------------------------------------------------------------------

def get_provider(cfg: "AppConfig") -> BaseProvider:
    """根据配置返回对应 Provider 实例。"""
    p = cfg.ai_provider.lower()
    if p == "zhipuai":
        return ZhipuAIProvider(api_key=cfg.ai_api_key, model=cfg.ai_model, base_url=cfg.ai_base_url)
    if p == "openai":
        return OpenAIProvider(
            api_key=cfg.ai_api_key,
            model=cfg.ai_model,
            base_url=cfg.ai_base_url,
        )
    if p == "ollama":
        return OllamaProvider(model=cfg.ai_model, base_url=cfg.ai_base_url)
    raise ValueError(f"未知的 ai_provider: '{cfg.ai_provider}'")


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def summarize_report(cfg: "AppConfig", report_text: str) -> str:
    """
    对日报文本调用 AI 总结（追加型，返回总结字符串）。
    若 ai_provider=disabled 或配置缺失则抛出 ValueError/RuntimeError。
    """
    if cfg.ai_provider.lower() == "disabled":
        raise ValueError("未启用 AI，请先在 config.json 中配置 ai_provider。")

    if cfg.ai_provider.lower() in ("zhipuai", "openai") and not cfg.ai_api_key:
        raise ValueError(
            f"ai_provider={cfg.ai_provider} 需要填写 ai_api_key，"
            "请在 config.json 中配置。"
        )

    provider = get_provider(cfg)
    prompt   = build_prompt(report_text)
    return provider.summarize(prompt)


def generate_full_report(cfg: "AppConfig", raw_report: str) -> str:
    """
    用 AI 全文重写日报。输入为机器生成的原始 Markdown，输出为 AI 重写后的完整日报文本。

    模板加载顺序：
      1. cfg.ai_prompt_template 指向的文件（如果存在）
      2. 内置默认模板 _DEFAULT_REPORT_TEMPLATE
    """
    if cfg.ai_provider.lower() == "disabled":
        raise ValueError("未启用 AI，请先在 config.json 中配置 ai_provider。")

    if cfg.ai_provider.lower() in ("zhipuai", "openai") and not cfg.ai_api_key:
        raise ValueError(
            f"ai_provider={cfg.ai_provider} 需要填写 ai_api_key，"
            "请在 config.json 中配置。"
        )

    # 加载模板
    template_path = cfg.ai_prompt_template
    if template_path and template_path.exists():
        template = template_path.read_text(encoding="utf-8")
    else:
        template = _DEFAULT_REPORT_TEMPLATE

    provider = get_provider(cfg)
    prompt   = build_report_prompt(template, raw_report)
    return provider.summarize(prompt)


def append_ai_summary(report_path: Path, summary_text: str, provider_name: str = "") -> None:
    """将 AI 总结追加写入已有日报 Markdown（第九章）。"""
    existing = report_path.read_text(encoding="utf-8")
    tag = f"（{provider_name}）" if provider_name else ""
    section = (
        "\n\n---\n\n"
        f"## 九、AI 智能总结{tag}\n\n"
        "> *以下内容由 AI 自动生成，仅供参考，请结合实际情况修改。*\n\n"
        f"{summary_text}\n"
    )
    report_path.write_text(existing + section, encoding="utf-8")
