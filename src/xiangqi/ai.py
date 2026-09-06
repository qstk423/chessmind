"""简易象棋 AI：极小极大 + 吃子启发。"""
from __future__ import annotations

import random
from copy import deepcopy

from src.xiangqi.rules import Move, XiangqiGame, evaluate_material, in_check, legal_moves

PIECE_VALUE = {"k": 10000, "r": 900, "c": 450, "n": 400, "b": 200, "a": 200, "p": 100}


def _order(game: XiangqiGame, moves: list[Move]) -> list[Move]:
    scored = []
    for mv in moves:
        captured = game.board[mv.tr][mv.tc]
        score = PIECE_VALUE.get((captured or "").lower(), 0)
        # 中心偏好
        score += 4 - abs(mv.tc - 4)
        scored.append((score, mv))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored]


def _search(game: XiangqiGame, depth: int, alpha: int, beta: int, maximizing: bool) -> int:
    if depth == 0 or game.result:
        score = evaluate_material(game.board)
        if in_check(game.board, "red"):
            score -= 35
        if in_check(game.board, "black"):
            score += 35
        return score

    moves = _order(game, legal_moves(game.board, game.turn))
    if not moves:
        return evaluate_material(game.board)

    if maximizing:
        best = -10**9
        for mv in moves[:28]:
            clone = deepcopy(game)
            clone.play_uci(mv.uci)
            best = max(best, _search(clone, depth - 1, alpha, beta, False))
            alpha = max(alpha, best)
            if beta <= alpha:
                break
        return best

    best = 10**9
    for mv in moves[:28]:
        clone = deepcopy(game)
        clone.play_uci(mv.uci)
        best = min(best, _search(clone, depth - 1, alpha, beta, True))
        beta = min(beta, best)
        if beta <= alpha:
            break
    return best


def choose_move(game: XiangqiGame, depth: int = 2) -> str | None:
    moves = _order(game, legal_moves(game.board, game.turn))
    if not moves:
        return None
    maximizing = game.turn == "red"
    best_score = -10**9 if maximizing else 10**9
    best: list[str] = []
    for mv in moves[:36]:
        clone = deepcopy(game)
        clone.play_uci(mv.uci)
        score = _search(clone, max(0, depth - 1), -10**9, 10**9, not maximizing)
        if maximizing:
            if score > best_score:
                best_score = score
                best = [mv.uci]
            elif score == best_score:
                best.append(mv.uci)
        else:
            if score < best_score:
                best_score = score
                best = [mv.uci]
            elif score == best_score:
                best.append(mv.uci)
    return random.choice(best) if best else moves[0].uci
