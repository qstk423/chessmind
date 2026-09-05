"""大模型选着 Agent——从合法着法中挑选，供算法对抗使用。"""
from __future__ import annotations

import asyncio
import json
import re
import time

from openai import AsyncOpenAI

from src.config import LLM_ENABLED, LLM_TIMEOUT_SEC
from src.llm_logger import log_llm_call

MOVE_PICKER_PROMPT = """你是国际象棋对弈 AI。你必须从给定的合法着法列表中选择一步棋。

硬性规则：
1. 只能输出列表中已有的 UCI 着法（例如 e2e4、e7e8q）
2. 禁止输出 SAN、注释、解释或多步着法
3. 优先考虑：王安全、子力得失、发展、中心控制
4. 若有将杀或得子机会，优先抓住

输出格式：仅一行 JSON，形如 {"uci":"e2e4","reason":"占领中心"}
reason 用中文，不超过 20 字。"""


class MovePickerAgent:
    """用 LLM 从合法着法中选一步；失败时由调用方回退引擎。"""

    def __init__(self, client: AsyncOpenAI | None, model: str):
        self.name = "选着Agent"
        self.client = client
        self.model = model

    async def pick_move(
        self,
        fen: str,
        legal_moves: list[str],
        move_history: list[str],
        grounding: str = "",
        engine_hint: str | None = None,
    ) -> dict:
        """
        返回 {"uci": str|None, "reason": str, "source": "llm"|"unavailable"|"parse_fail"}
        """
        if not legal_moves:
            return {"uci": None, "reason": "无合法着法", "source": "unavailable"}

        if not LLM_ENABLED or self.client is None:
            return {"uci": None, "reason": "未配置 LLM", "source": "unavailable"}

        history_text = " ".join(move_history[-12:]) if move_history else "开局"
        # 合法着法过多时截断提示（但仍要求从完整列表选——实际上传全量）
        legal_text = ", ".join(legal_moves)
        hint = f"\n引擎参考着法（可选参考，非必须）：{engine_hint}" if engine_hint else ""
        user_prompt = (
            f"当前 FEN：{fen}\n"
            f"最近走法：{history_text}\n"
            f"合法着法 UCI 列表：{legal_text}\n"
            f"{('结构化局面信息：\n' + grounding) if grounding else ''}"
            f"{hint}\n"
            "请选择一步棋，只输出 JSON。"
        )

        t0 = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": MOVE_PICKER_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=80,
                ),
                timeout=LLM_TIMEOUT_SEC,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            usage = getattr(response, "usage", None)
            raw = (response.choices[0].message.content or "").strip()
            log_llm_call(
                agent=self.name,
                model=self.model,
                success=True,
                latency_ms=latency_ms,
                prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
                total_tokens=getattr(usage, "total_tokens", None) if usage else None,
                extra={"raw_preview": raw[:120]},
            )
            uci, reason = self._parse_choice(raw, legal_moves)
            if uci is None:
                return {"uci": None, "reason": reason or "解析失败", "source": "parse_fail", "raw": raw}
            return {"uci": uci, "reason": reason, "source": "llm", "raw": raw}
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            log_llm_call(
                agent=self.name,
                model=self.model,
                success=False,
                latency_ms=latency_ms,
                error=f"{type(e).__name__}: {e}",
            )
            return {"uci": None, "reason": f"调用失败: {type(e).__name__}", "source": "unavailable"}

    @staticmethod
    def _parse_choice(raw: str, legal_moves: list[str]) -> tuple[str | None, str]:
        legal_set = set(legal_moves)

        # 尝试 JSON
        try:
            # 抽取第一个 {...}
            m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
            if m:
                obj = json.loads(m.group(0))
                uci = str(obj.get("uci", "")).strip().lower()
                reason = str(obj.get("reason", "")).strip() or "LLM 选着"
                if uci in legal_set:
                    return uci, reason
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

        # 回退：在文本中找合法 UCI
        for move in sorted(legal_moves, key=len, reverse=True):
            if re.search(rf"\b{re.escape(move)}\b", raw, re.IGNORECASE):
                return move, "从回复中提取 UCI"

        return None, "回复中无合法 UCI"
