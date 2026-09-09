"""象棋 LLM 选着（GLM / 千问），失败由调用方回退引擎。"""
from __future__ import annotations

from typing import Literal

from src.agents.move_picker import XIANGQI_MOVE_PICKER_PROMPT, MovePickerAgent
from src.config import LLM_MODEL, QWEN_MODEL
from src.llm_client import make_llm_client, make_qwen_client
from src.xiangqi.rules import XiangqiGame, legal_moves

Which = Literal["llm", "qwen"]


async def pick_xiangqi_move(game: XiangqiGame, *, which: Which = "llm") -> dict:
    legal = [mv.uci for mv in legal_moves(game.board, game.turn)]
    if not legal:
        return {"uci": None, "reason": "无合法着法", "source": "unavailable"}

    if which == "qwen":
        client = make_qwen_client()
        model = QWEN_MODEL
    else:
        client = make_llm_client()
        model = LLM_MODEL

    history = [m.get("uci") or "" for m in (game.history or []) if m.get("uci")]
    # 引擎参考着（浅）：优先 Pikafish，失败则跳过
    engine_hint = None
    try:
        from src.xiangqi.engine import best_move_pikafish, pikafish_available

        if pikafish_available():
            engine_hint = best_move_pikafish(game.fen(), depth=10)
            if engine_hint and engine_hint not in legal:
                engine_hint = None
    except Exception:
        engine_hint = None

    picker = MovePickerAgent(client, model, system_prompt=XIANGQI_MOVE_PICKER_PROMPT)
    return await picker.pick_move(
        fen=game.fen(),
        legal_moves=legal,
        move_history=history[-16:],
        grounding=f"行棋方：{'红' if game.turn == 'red' else '黑'}",
        engine_hint=engine_hint,
    )
