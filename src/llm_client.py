"""OpenAI 兼容 LLM 调用封装（GLM-5.1 + 可选千问）。

对局选着 / Council 在智谱侧默认关闭 thinking；千问不传 thinking 字段。
"""
from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from src.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_ENABLED,
    LLM_MODEL,
    LLM_THINKING,
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_ENABLED,
)


def make_llm_client() -> AsyncOpenAI | None:
    if not LLM_ENABLED:
        return None
    return AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def make_qwen_client() -> AsyncOpenAI | None:
    if not QWEN_ENABLED:
        return None
    return AsyncOpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)


def _is_zhipu_client(client: AsyncOpenAI) -> bool:
    base = str(getattr(client, "base_url", "") or "").lower()
    return "bigmodel.cn" in base or "zhipuai" in base or "zhipu" in base


def _thinking_extra() -> dict[str, Any]:
    """智谱 GLM-5.x 支持 thinking；对局/结构化输出默认关闭。"""
    mode = (LLM_THINKING or "disabled").strip().lower()
    if mode in ("1", "true", "yes", "on", "enabled", "enable"):
        return {"thinking": {"type": "enabled"}}
    if mode in ("0", "false", "no", "off", "disabled", "disable", "none"):
        return {"thinking": {"type": "disabled"}}
    return {}


def message_text(message: Any) -> str:
    """从 chat.completion message 取可见文本（兼容 reasoning 字段）。"""
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        joined = "".join(parts).strip()
        if joined:
            return joined
    for key in ("reasoning_content", "reasoning"):
        alt = getattr(message, key, None)
        if isinstance(alt, str) and alt.strip():
            return alt.strip()
    return (content or "").strip() if isinstance(content, str) else ""


async def chat_completion(
    client: AsyncOpenAI,
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float = 0.35,
    max_tokens: int = 700,
    extra_body: dict[str, Any] | None = None,
):
    """统一 chat.completions.create；仅智谱客户端附加 thinking。"""
    body: dict[str, Any] = {}
    if _is_zhipu_client(client):
        body.update(_thinking_extra())
    if extra_body:
        body.update(extra_body)
    kwargs: dict[str, Any] = {
        "model": model or LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if body:
        kwargs["extra_body"] = body
    return await client.chat.completions.create(**kwargs)
