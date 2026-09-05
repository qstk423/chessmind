"""多模态：棋盘照片 / 截图 → FEN（视觉大模型）。"""
from __future__ import annotations

import asyncio
import base64
import re
import time
from typing import Any, Literal

import chess
from openai import AsyncOpenAI

from src.config import LLM_API_KEY, LLM_BASE_URL, LLM_ENABLED, LLM_TIMEOUT_SEC, VISION_MODEL
from src.llm_logger import log_llm_call

FEN_PROMPT = """你是国际象棋棋盘视觉识别专家。用户拍了一张实体棋盘或屏幕截图。

任务：识别盘上每个格子的棋子，输出标准 FEN（一行）。

坐标约定（非常重要）：
- 白方在下方时：左下角为 a1（深色格通常在右下角 h1 一侧因棋盘而异，以行列为准）
- 若照片里靠近拍摄者的是黑方底线，仍按「白方在 FEN 第 8 段」的标准输出，即 FEN 第一段是黑方底线（第 8 横线）
- 白棋大写：K Q R B N P；黑棋小写：k q r b n p；空格用数字合并

输出要求：
1. 只输出一行 FEN：棋子段 + 空格 + 行棋方(w/b) + 易位(KQkq或-) + 吃过路兵 + 半回合 + 回合数
2. 看不清的格子按最可能猜测，但必须语法合法
3. 不要 Markdown、不要解释、不要代码块

示例：
rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1
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
    text = text.strip().strip("`")
    m = re.search(
        r"([rnbqkpRNBQKP1-8]+/){7}[rnbqkpRNBQKP1-8]+\s+[wb]\s+(?:K?Q?k?q?|-)\s+(?:[a-h][36]|-)\s+\d+\s+\d+",
        text,
    )
    if m:
        return m.group(0).strip()
    m2 = re.search(r"([rnbqkpRNBQKP1-8]+/){7}[rnbqkpRNBQKP1-8]+(?:\s+[wb].*)?", text)
    if m2:
        fen = m2.group(0).strip()
        parts = fen.split()
        if len(parts) == 1:
            fen = parts[0] + " w - - 0 1"
        elif len(parts) < 6:
            while len(parts) < 6:
                parts.append("0" if len(parts) >= 4 else "-")
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


def apply_side_to_move(fen: str, side: Literal["w", "b", "white", "black"] | None) -> str:
    if not side:
        return fen
    s = side.strip().lower()
    turn = "w" if s in ("w", "white") else "b" if s in ("b", "black") else None
    if not turn:
        return fen
    parts = fen.split()
    if len(parts) < 2:
        return fen
    parts[1] = turn
    try:
        return chess.Board(" ".join(parts)).fen()
    except ValueError:
        return fen


async def fen_from_image_bytes(
    raw: bytes,
    *,
    filename: str | None = None,
    client: AsyncOpenAI | None = None,
    side_to_move: str | None = None,
    extra_hint: str | None = None,
) -> dict[str, Any]:
    if not LLM_ENABLED:
        return {"ok": False, "error": "未配置 LLM_API_KEY，无法进行多模态识别"}

    # 手机原图可能很大，限制体积（调用方也可先压缩）
    if len(raw) > 12 * 1024 * 1024:
        return {"ok": False, "error": "图片过大（限制 12MB），请压缩后再试"}

    own_client = client or AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    mime = _guess_mime(filename, raw)
    b64 = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    prompt = FEN_PROMPT
    if extra_hint:
        prompt += f"\n\n用户补充：{extra_hint}"
    if side_to_move in ("w", "b", "white", "black"):
        side_zh = "白方" if side_to_move in ("w", "white") else "黑方"
        prompt += f"\n\n行棋方请设为：{side_zh}（FEN 第二段为 {'w' if side_zh == '白方' else 'b'}）。"

    t0 = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            own_client.chat.completions.create(
                model=VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                temperature=0.1,
                max_tokens=160,
            ),
            timeout=LLM_TIMEOUT_SEC,
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
        return {
            "ok": False,
            "error": f"视觉模型调用失败：{type(e).__name__}: {e}",
            "vision_model": VISION_MODEL,
            "hint": "请确认已开通视觉模型，并在 .env 设置 VISION_MODEL（如 qwen-vl-plus）",
        }

    fen = extract_fen_candidate(raw_text)
    if not fen:
        return {"ok": False, "error": "未能从模型回复中解析 FEN", "raw": raw_text[:300]}

    fen = apply_side_to_move(fen, side_to_move)
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
