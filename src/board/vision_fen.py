"""多模态：棋盘截图 → FEN（视觉大模型）。"""
from __future__ import annotations

import base64
import re
import time
from typing import Any

import chess
from openai import AsyncOpenAI

from src.config import LLM_API_KEY, LLM_BASE_URL, LLM_ENABLED, VISION_MODEL
from src.llm_logger import log_llm_call

FEN_PROMPT = """你是国际象棋棋盘识别专家。请根据图片中的棋盘，输出标准 FEN。

要求：
1. 只输出一行 FEN（8段棋子 + 行棋方 + 易位权 + 吃过路兵 + 半回合 + 回合数）
2. 若看不清某格，按最可能配置猜测，但必须输出合法 FEN
3. 不要输出 Markdown 或解释

示例格式：
rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1
"""


def _guess_mime(filename: str | None, raw: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".png") or raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def extract_fen_candidate(text: str) -> str | None:
    if not text:
        return None
    # 常见 FEN 形态
    m = re.search(
        r"([rnbqkpRNBQKP1-8]+/){7}[rnbqkpRNBQKP1-8]+\s+[wb]\s+(?:K?Q?k?q?|-)\s+(?:[a-h][36]|-)\s+\d+\s+\d+",
        text,
    )
    if m:
        return m.group(0).strip()
    # 宽松：至少棋盘 8 段
    m2 = re.search(r"([rnbqkpRNBQKP1-8]+/){7}[rnbqkpRNBQKP1-8]+(?:\s+[wb].*)?", text)
    if m2:
        fen = m2.group(0).strip()
        parts = fen.split()
        if len(parts) == 1:
            fen = parts[0] + " w - - 0 1"
        elif len(parts) < 6:
            # pad
            while len(parts) < 6:
                parts.append("0" if len(parts) >= 4 else "-")
            # fix turn if missing
            if parts[1] not in ("w", "b"):
                parts.insert(1, "w")
            fen = " ".join(parts[:6])
        return fen
    return None


def validate_fen(fen: str) -> tuple[bool, str | None]:
    try:
        board = chess.Board(fen)
        return True, board.fen()
    except ValueError as e:
        return False, str(e)


async def fen_from_image_bytes(
    raw: bytes,
    *,
    filename: str | None = None,
    client: AsyncOpenAI | None = None,
) -> dict[str, Any]:
    if not LLM_ENABLED:
        return {"ok": False, "error": "未配置 LLM_API_KEY，无法进行多模态识别"}

    own_client = client or AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    mime = _guess_mime(filename, raw)
    b64 = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    t0 = time.perf_counter()
    try:
        resp = await own_client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": FEN_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=120,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        usage = getattr(resp, "usage", None)
        log_llm_call(
            agent="vision_fen",
            model=VISION_MODEL,
            success=True,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", None) if usage else None,
        )
        raw_text = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        log_llm_call(
            agent="vision_fen",
            model=VISION_MODEL,
            success=False,
            latency_ms=latency_ms,
            error=f"{type(e).__name__}: {e}",
        )
        return {"ok": False, "error": f"视觉模型调用失败：{type(e).__name__}: {e}"}

    fen = extract_fen_candidate(raw_text)
    if not fen:
        return {"ok": False, "error": "未能从模型回复中解析 FEN", "raw": raw_text[:300]}

    ok, normalized = validate_fen(fen)
    if not ok:
        return {"ok": False, "error": f"FEN 非法：{normalized}", "raw": raw_text[:300], "fen_guess": fen}

    return {
        "ok": True,
        "fen": normalized,
        "raw": raw_text[:300],
        "vision_model": VISION_MODEL,
        "latency_ms": round(latency_ms, 1),
    }
