"""Agent 基类——文本分析 + 结构化 JSON 分析（含调用日志）"""
from __future__ import annotations

import asyncio
import time

from openai import AsyncOpenAI

from src.agents.schema import AgentOpinion, fallback_opinion, opinion_from_raw
from src.config import LLM_ENABLED, LLM_TIMEOUT_SEC
from src.llm_logger import log_llm_call


class BaseAgent:
    """所有分析 Agent 的基类"""

    agent_id: str = "base"

    def __init__(self, name: str, role_prompt: str, client: AsyncOpenAI | None, model: str):
        self.name = name
        self.role_prompt = role_prompt
        self.client = client
        self.model = model

    async def analyze(self, fen: str, move_history: list[str], extra_context: str = "") -> str:
        """兼容旧接口：返回自然语言（或 JSON 字符串）。"""
        opinion = await self.analyze_structured(fen, move_history, extra_context)
        if opinion.parse_ok:
            return opinion.summary
        return opinion.raw_text or opinion.summary

    async def analyze_structured(
        self,
        fen: str,
        move_history: list[str],
        extra_context: str = "",
        *,
        temperature: float = 0.35,
        max_tokens: int = 700,
    ) -> AgentOpinion:
        if not LLM_ENABLED or self.client is None:
            return fallback_opinion(
                self.agent_id,
                "llm_disabled",
                "未配置 LLM_API_KEY，Agent 分析已跳过；引擎评分与走子分类不受影响。",
            )

        history_text = " ".join(move_history) if move_history else "开局"
        user_prompt = self._build_prompt(fen, history_text, extra_context)

        t0 = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.role_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=LLM_TIMEOUT_SEC,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            usage = getattr(response, "usage", None)
            log_llm_call(
                agent=self.name,
                model=self.model,
                success=True,
                latency_ms=latency_ms,
                prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
                total_tokens=getattr(usage, "total_tokens", None) if usage else None,
            )
            raw = response.choices[0].message.content or ""
            return opinion_from_raw(self.agent_id, raw)
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            log_llm_call(
                agent=self.name,
                model=self.model,
                success=False,
                latency_ms=latency_ms,
                error=f"{type(e).__name__}: {e}",
            )
            return fallback_opinion(
                self.agent_id,
                f"{type(e).__name__}",
                f"{self.name}调用失败：{type(e).__name__}，请检查 LLM 配置。",
            )

    async def chat_raw(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.4,
        max_tokens: int = 500,
        agent_label: str | None = None,
    ) -> str:
        """自由文本调用（辩论回合等）。失败返回错误说明。"""
        label = agent_label or self.name
        if not LLM_ENABLED or self.client is None:
            return f"（{label}跳过：未配置 LLM）"
        t0 = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=LLM_TIMEOUT_SEC,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            usage = getattr(response, "usage", None)
            log_llm_call(
                agent=label,
                model=self.model,
                success=True,
                latency_ms=latency_ms,
                prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
                total_tokens=getattr(usage, "total_tokens", None) if usage else None,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            log_llm_call(
                agent=label,
                model=self.model,
                success=False,
                latency_ms=latency_ms,
                error=f"{type(e).__name__}: {e}",
            )
            return f"（{label}调用失败：{type(e).__name__}）"

    def _build_prompt(self, fen: str, history_text: str, extra_context: str) -> str:
        parts = []
        if fen:
            parts.append(f"当前棋盘 FEN：{fen}")
        parts.append(f"最近走法历史：{history_text}")
        if extra_context:
            parts.append(
                "结构化局面信息（程序提取的确定性事实，必须以此为准）：\n" + extra_context
            )
        parts.append("请给出你的分析（按系统要求输出 JSON）。")
        return "\n\n".join(parts)
