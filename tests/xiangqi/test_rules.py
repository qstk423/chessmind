"""规则引擎基础测试：困毙、FEN、UCI。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.xiangqi.rules import START_FEN, Move, XiangqiGame, parse_fen


def test_from_uci_rejects_bad():
    with pytest.raises(ValueError):
        Move.from_uci("z9z9")
    with pytest.raises(ValueError):
        Move.from_uci("e")
    with pytest.raises(ValueError):
        Move.from_uci("e2e9x")


def test_parse_fen_rejects_unknown_piece():
    bad = START_FEN.replace("R", "x", 1)
    with pytest.raises(ValueError, match="非法棋子"):
        parse_fen(bad)


def test_parse_fen_requires_kings():
    fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBA1ABNR w - - 0 1"
    with pytest.raises(ValueError, match="帅/将"):
        parse_fen(fen)


def test_reset_evaluates_terminal_fen():
    # 红车已锁宫，黑将无路：加载后应直接判红胜绝杀
    game = XiangqiGame("3k5/9/9/9/9/9/9/9/9/3RK4 b - - 0 1")
    assert game.result is not None
    assert "绝杀" in game.result


def test_stalemate_is_loss_not_draw():
    game = XiangqiGame()
    with patch("src.xiangqi.rules.legal_moves", return_value=[]), patch("src.xiangqi.rules.in_check", return_value=False):
        game._refresh_result()
    assert game.result is not None
    assert "困毙" in game.result
    assert "和" not in game.result


def test_undo_restores_halfmove():
    game = XiangqiGame()
    before = game.halfmove
    entry = game.play_uci("b0c2")
    assert game.halfmove == before + 1
    game.undo()
    assert game.halfmove == before
    assert "halfmove_before" in entry


def test_threefold_repetition_is_draw():
    game = XiangqiGame()
    key = game.position_key()
    # 伪造三次同一局面出现在历史中
    fake_fen = game.fen()
    game.history = [
        {"fen": fake_fen, "color": "red", "gave_check": False},
        {"fen": fake_fen, "color": "black", "gave_check": False},
        {"fen": fake_fen, "color": "red", "gave_check": False},
    ]
    with patch("src.xiangqi.rules.legal_moves", return_value=[Move.from_uci("b0c2")]):
        game._refresh_result()
    assert game.result == "和棋 · 重复局面"
    assert key == game.position_key()


def test_perpetual_check_loses():
    game = XiangqiGame()
    fen = game.fen()
    # 长将天然伴随重复局面，必须优先判长将方负，而不是和棋。
    game.history = [
        {"fen": fen, "color": "red", "gave_check": True},
        {"fen": fen, "color": "black", "gave_check": False},
        {"fen": fen, "color": "red", "gave_check": True},
        {"fen": fen, "color": "black", "gave_check": False},
        {"fen": fen, "color": "red", "gave_check": True},
        {"fen": fen, "color": "black", "gave_check": False},
        {"fen": fen, "color": "red", "gave_check": True},
    ]
    with patch("src.xiangqi.rules.legal_moves", return_value=[Move.from_uci("b0c2")]):
        game._refresh_result()
    assert game.result == "黑方胜 · 长将"
