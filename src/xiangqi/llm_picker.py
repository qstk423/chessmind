"""象棋 LLM 选着（GLM / 千问），失败由调用方回退引擎。"""
from __future__ import annotations

import asyncio
from typing import Literal

from src.agents.move_picker import XIANGQI_MOVE_PICKER_PROMPT, MovePickerAgent
from src.config import LLM_MODEL, QWEN_MODEL
from src.llm_client import make_llm_client, make_qwen_client
from src.xiangqi.rules import XiangqiGame, legal_moves


Which = Literal["llm", "qwen"]


def _cheap_null_retract(game: XiangqiGame, uci: str) -> bool:
    """避免循环 import：本地做「无吃子原路退回」判断。"""
    from src.xiangqi.rules import Move

    try:
        mv = Move.from_uci(uci)
    except Exception:
        return False
    for e in reversed(game.history):
        if e.get("color") != game.turn:
            continue
        prev_from, prev_to = e.get("from"), e.get("to")
        if not prev_from or not prev_to:
            return False
        if [mv.fr, mv.fc] == list(prev_to) and [mv.tr, mv.tc] == list(prev_from):
            return not bool(game.board[mv.tr][mv.tc])
        return False
    return False


async def pick_xiangqi_move(
    game: XiangqiGame, *, which: Which = "llm", strength: str = "normal"
) -> dict:
    all_legal = [mv.uci for mv in legal_moves(game.board, game.turn)]
    if not all_legal:
        return {"uci": None, "reason": "无合法着法", "source": "unavailable"}

    # 有其它着法时，不把「原路退回」交给模型选
    legal = [u for u in all_legal if not _cheap_null_retract(game, u)]
    if not legal:
        legal = all_legal

    if which == "qwen":
        client = make_qwen_client()
        model = QWEN_MODEL
    else:
        client = make_llm_client()
        model = LLM_MODEL

    history = [m.get("uci") or "" for m in (game.history or []) if m.get("uci")]
    engine_hint = None
    engine_candidates: list[tuple[str, int | None]] = []
    try:
        from src.xiangqi.ai import PIKAFISH_DEPTH, PIKAFISH_MOVETIME_MS, PIKAFISH_MULTIPV
        from src.xiangqi.engine import candidate_moves_pikafish, pikafish_available

        if pikafish_available():
            level = strength if strength in PIKAFISH_DEPTH else "normal"
            engine_candidates = await asyncio.to_thread(
                candidate_moves_pikafish,
                game.fen(),
                depth=PIKAFISH_DEPTH[level],
                movetime_ms=PIKAFISH_MOVETIME_MS[level],
                multipv=PIKAFISH_MULTIPV[level],
            )
            engine_hint = engine_candidates[0][0] if engine_candidates else None
            if engine_hint and engine_hint not in legal:
                if engine_hint not in all_legal:
                    engine_hint = None
    except Exception:
        engine_hint = None

    picker = MovePickerAgent(client, model, system_prompt=XIANGQI_MOVE_PICKER_PROMPT)
    pick = await picker.pick_move(
        fen=game.fen(),
        legal_moves=legal,
        move_history=history[-16:],
        grounding=(
            f"行棋方：{'红' if game.turn == 'red' else '黑'}\n"
            "禁止无意义地把刚走过的子原路退回；优先发展、得子与将军。"
        ),
        engine_hint=engine_hint,
    )
    pick["engine_candidates"] = engine_candidates
    return pick
