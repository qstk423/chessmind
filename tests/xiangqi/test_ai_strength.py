"""三档选着与模型送子保护。"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from src.xiangqi.ai import (
    _gifts_undefended_piece,
    acceptable_engine_moves,
    choose_move,
    choose_move_builtin,
    choose_move_for_side,
)
from src.xiangqi.rules import XiangqiGame


def test_three_strengths_have_distinct_safe_candidate_ranges() -> None:
    candidates = [
        ("b2e2", 40),
        ("h2e2", 0),
        ("b0c2", -100),
        ("a3a4", -250),
    ]
    assert acceptable_engine_moves(candidates, "hard") == ["b2e2"]
    assert acceptable_engine_moves(candidates, "normal") == ["b2e2", "h2e2"]
    assert acceptable_engine_moves(candidates, "easy") == ["b2e2", "h2e2", "b0c2"]


def test_llm_move_below_safety_line_uses_engine() -> None:
    async def bad_pick(*_args, **_kwargs) -> dict:
        return {
            "uci": "a3a4",
            "reason": "随手推进",
            "engine_candidates": [("b2e2", 50), ("a3a4", -300)],
        }

    with patch("src.xiangqi.llm_picker.pick_xiangqi_move", bad_pick):
        result = asyncio.run(
            choose_move_for_side(XiangqiGame(), ai_side="llm", strength="normal")
        )
    assert result["uci"] == "b2e2"
    assert result["source"] == "engine_safety"


def test_llm_move_within_easy_range_remains_model_choice() -> None:
    async def acceptable_pick(*_args, **_kwargs) -> dict:
        return {
            "uci": "h2e2",
            "reason": "出炮",
            "engine_candidates": [("b2e2", 50), ("h2e2", -40)],
        }

    with patch("src.xiangqi.llm_picker.pick_xiangqi_move", acceptable_pick):
        result = asyncio.run(
            choose_move_for_side(XiangqiGame(), ai_side="llm", strength="easy")
        )
    assert result["uci"] == "h2e2"
    assert result["source"] == "llm"


def _rook_sacrifice_position() -> XiangqiGame:
    """2026-09-28 实盘：黑车回防是最佳着，吃 d1 马会白送一车。"""
    game = XiangqiGame()
    for uci in (
        "g3g4", "h7g7", "c0e2", "h9i7", "h0g2", "b7e7",
        "b0d1", "i9h9", "g2f4", "a9a8", "a0a1", "a8f8",
        "f4e6", "f8f6", "e6d4", "f6d6", "d4f5",
    ):
        game.play_uci(uci)
    return game


def test_hard_engine_may_return_to_avoid_rook_sacrifice() -> None:
    game = _rook_sacrifice_position()
    assert _gifts_undefended_piece(game, "d6d1") is True

    # d6-f6 恰好是黑车上一手的原路回防，但它是强引擎的最佳着。
    with (
        patch("src.xiangqi.engine.pikafish_available", return_value=True),
        patch(
            "src.xiangqi.engine.candidate_moves_pikafish",
            return_value=[("d6f6", 61)],
        ),
    ):
        assert choose_move(game, strength="hard") == "d6f6"


def test_builtin_hard_fallback_rejects_uncompensated_rook_sacrifice() -> None:
    game = _rook_sacrifice_position()
    move = choose_move_builtin(game, strength="hard")
    assert move != "d6d1"
    assert move is not None
    assert _gifts_undefended_piece(game, move) is False
