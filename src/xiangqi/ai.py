"""象棋选着：优先 Pikafish（若可用），否则强化内建搜索。

内建引擎相对旧版：
- 开局库（避免开局乱吃子「炮打马」）
- 子力 + 位置分 + 机动性
- 吃子 / 将军平静搜索（quiescence），防止贪吃被反吃
- 用 play/undo 代替整盘 deepcopy，加深默认可达 4~5 层
"""
from __future__ import annotations

import random
from typing import Literal

from src.xiangqi.rules import (
    START_FEN,
    Move,
    XiangqiGame,
    evaluate_material,
    in_check,
    is_legal,
    legal_moves,
    position_key_from_fen,
)

PIECE_VALUE = {"k": 10000, "r": 1000, "c": 450, "n": 450, "b": 200, "a": 200, "p": 100}

# 简化位置分：兵过河、马炮居中、车占直线加权（红方视角，黑方镜像）
_PST_PAWN = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [10, 20, 30, 40, 40, 40, 30, 20, 10],
    [20, 30, 40, 50, 50, 50, 40, 30, 20],
    [30, 40, 50, 60, 60, 60, 50, 40, 30],
    [10, 20, 20, 30, 30, 30, 20, 20, 10],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
]
_CENTER = [2, 4, 8, 10, 12, 10, 8, 4, 2]

Strength = Literal["easy", "normal", "hard"]

STRENGTH_DEPTH = {"easy": 2, "normal": 4, "hard": 5}
STRENGTH_NODES = {"easy": 24, "normal": 48, "hard": 72}

# 开局库：局面键（布局+行棋方）→ 候选 UCI。刻意避开早期无保护「炮打马」。
_OPENING_BOOK: dict[str, list[str]] = {
    position_key_from_fen(START_FEN): ["b2e2", "h2e2", "b0c2", "h0g2", "a3a4", "i3i4"],
}
# 红炮二平五后，常见黑应
_OPENING_BOOK[position_key_from_fen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR b")] = [
    "h7e7",
    "b7e7",
    "b9c7",
    "h9g7",
]
_OPENING_BOOK[position_key_from_fen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/4C2C1/9/RNBAKABNR b")] = [
    "b7e7",
    "h7e7",
    "h9g7",
    "b9c7",
]


def _pst(piece: str, r: int, c: int) -> int:
    kind = piece.lower()
    rr, sign = (r, 1) if piece.isupper() else (9 - r, -1)
    bonus = 0
    if kind == "p":
        bonus = _PST_PAWN[rr][c]
    elif kind in ("n", "c"):
        bonus = _CENTER[c] + (4 if 3 <= rr <= 6 else 0)
    elif kind == "r":
        bonus = 6 if c in (0, 8) else 10
    elif kind in ("a", "b"):
        bonus = 4
    return sign * bonus


def evaluate_position(game: XiangqiGame) -> int:
    """正分偏红。"""
    if game.result:
        if "红方胜" in game.result:
            return 50_000
        if "黑方胜" in game.result:
            return -50_000
        return 0
    score = evaluate_material(game.board)
    board = game.board
    for r in range(10):
        for c in range(9):
            p = board[r][c]
            if p:
                score += _pst(p, r, c)
    # 机动性：合法着数差（浅）
    red_mob = len(legal_moves(board, "red"))
    black_mob = len(legal_moves(board, "black"))
    score += (red_mob - black_mob) * 2
    if in_check(board, "red"):
        score -= 45
    if in_check(board, "black"):
        score += 45
    return score


def _capture_value(board, mv: Move) -> int:
    cap = board[mv.tr][mv.tc]
    return PIECE_VALUE.get((cap or "").lower(), 0)


def _is_safe_capture(game: XiangqiGame, mv: Move) -> bool:
    """粗略：吃完后该格若能被对方立刻吃回且我方子不值当，则不安全。"""
    cap_val = _capture_value(game.board, mv)
    if cap_val == 0:
        return True
    piece = game.board[mv.fr][mv.fc]
    my_val = PIECE_VALUE.get((piece or "").lower(), 0)
    game.play_uci(mv.uci)
    opp = game.turn
    recapture = False
    for om in legal_moves(game.board, opp):
        if om.tr == mv.tr and om.tc == mv.tc:
            recapture = True
            break
    game.undo()
    if not recapture:
        return True
    # 用低换高 OK；等换或亏换不优先
    return cap_val > my_val


def _order(game: XiangqiGame, moves: list[Move]) -> list[Move]:
    scored: list[tuple[int, Move]] = []
    for mv in moves:
        score = _capture_value(game.board, mv) * 10
        score += 6 - abs(mv.tc - 4)
        if game.board[mv.tr][mv.tc]:
            if not _is_safe_capture(game, mv):
                score -= 350  # 惩罚开局式「炮打马」被反吃
            else:
                score += 80
        # 将军加分
        game.play_uci(mv.uci)
        if in_check(game.board, game.turn):
            score += 55
        game.undo()
        scored.append((score, mv))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored]


def _quiescence(game: XiangqiGame, alpha: int, beta: int, maximizing: bool, qdepth: int) -> int:
    stand = evaluate_position(game)
    if qdepth <= 0 or game.result:
        return stand
    if maximizing:
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
    else:
        if stand <= alpha:
            return stand
        beta = min(beta, stand)

    moves = legal_moves(game.board, game.turn)
    noisy: list[Move] = []
    for mv in moves:
        if game.board[mv.tr][mv.tc]:
            noisy.append(mv)
            continue
        game.play_uci(mv.uci)
        checks = in_check(game.board, game.turn)
        game.undo()
        if checks:
            noisy.append(mv)
    noisy = _order(game, noisy)[:20]
    if not noisy:
        return stand

    if maximizing:
        best = stand
        for mv in noisy:
            game.play_uci(mv.uci)
            best = max(best, _quiescence(game, alpha, beta, False, qdepth - 1))
            game.undo()
            alpha = max(alpha, best)
            if beta <= alpha:
                break
        return best
    best = stand
    for mv in noisy:
        game.play_uci(mv.uci)
        best = min(best, _quiescence(game, alpha, beta, True, qdepth - 1))
        game.undo()
        beta = min(beta, best)
        if beta <= alpha:
            break
    return best


def _search(
    game: XiangqiGame,
    depth: int,
    alpha: int,
    beta: int,
    maximizing: bool,
    node_cap: list[int],
) -> int:
    if node_cap[0] <= 0:
        return evaluate_position(game)
    node_cap[0] -= 1
    if game.result:
        return evaluate_position(game)
    if depth == 0:
        return _quiescence(game, alpha, beta, maximizing, qdepth=4)

    moves = _order(game, legal_moves(game.board, game.turn))
    if not moves:
        return evaluate_position(game)

    if maximizing:
        best = -10**9
        for mv in moves:
            game.play_uci(mv.uci)
            best = max(best, _search(game, depth - 1, alpha, beta, False, node_cap))
            game.undo()
            alpha = max(alpha, best)
            if beta <= alpha:
                break
        return best

    best = 10**9
    for mv in moves:
        game.play_uci(mv.uci)
        best = min(best, _search(game, depth - 1, alpha, beta, True, node_cap))
        game.undo()
        beta = min(beta, best)
        if beta <= alpha:
            break
    return best


def _book_move(game: XiangqiGame) -> str | None:
    if len(game.history) > 6:
        return None
    key = game.position_key()
    cands = _OPENING_BOOK.get(key) or []
    legal = {m.uci for m in legal_moves(game.board, game.turn)}
    ok = [u for u in cands if u in legal]
    if not ok:
        return None
    return random.choice(ok)


def choose_move_builtin(game: XiangqiGame, *, strength: Strength = "normal") -> str | None:
    book = _book_move(game)
    if book:
        return book

    depth = STRENGTH_DEPTH.get(strength, 4)
    widen = STRENGTH_NODES.get(strength, 48)
    moves = _order(game, legal_moves(game.board, game.turn))[:widen]
    if not moves:
        return None

    maximizing = game.turn == "red"
    best_score = -10**9 if maximizing else 10**9
    best: list[str] = []
    node_budget = [12_000 if strength == "easy" else (40_000 if strength == "normal" else 90_000)]

    for mv in moves:
        game.play_uci(mv.uci)
        score = _search(game, max(0, depth - 1), -10**9, 10**9, not maximizing, node_budget)
        game.undo()
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


def choose_move(
    game: XiangqiGame,
    depth: int | None = None,
    *,
    strength: Strength | None = None,
) -> str | None:
    """统一入口：有 Pikafish 用引擎，否则用强化内建。"""
    level: Strength = strength or "normal"
    if depth is not None:
        # 兼容旧接口 depth=1..5 → 档位
        if depth <= 2:
            level = "easy"
        elif depth >= 5:
            level = "hard"
        else:
            level = "normal"

    try:
        from src.xiangqi.engine import best_move_pikafish, pikafish_available

        if pikafish_available():
            eng_depth = {"easy": 8, "normal": 14, "hard": 18}[level]
            mv = best_move_pikafish(game.fen(), depth=eng_depth)
            if mv and is_legal(game.board, Move.from_uci(mv), game.turn):
                return mv
    except Exception:
        pass

    return choose_move_builtin(game, strength=level)
