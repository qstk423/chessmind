"""象棋选着：优先 Pikafish（若可用），否则强化内建搜索。

内建引擎相对旧版：
- 开局库（避免开局乱吃子「炮打马」）
- 子力 + 位置分 + 机动性
- 吃子 / 将军平静搜索（quiescence），防止贪吃被反吃
- 用 play/undo 代替整盘 deepcopy，加深默认可达 4~5 层
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
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

# 内建只作 Pikafish 失败兜底；三个档位用候选范围和允许分差拉开强度。
STRENGTH_DEPTH = {"easy": 1, "normal": 2, "hard": 3}
STRENGTH_NODES = {"easy": 12, "normal": 20, "hard": 28}
STRENGTH_NODE_BUDGET = {"easy": 2_500, "normal": 8_000, "hard": 20_000}
STRENGTH_TIME_BUDGET = {"easy": 0.4, "normal": 0.9, "hard": 1.8}
PIKAFISH_DEPTH = {"easy": 10, "normal": 16, "hard": 22}
PIKAFISH_MOVETIME_MS = {"easy": 250, "normal": 750, "hard": 1500}
PIKAFISH_MULTIPV = {"easy": 4, "normal": 2, "hard": 1}
PIKAFISH_MAX_LOSS_CP = {"easy": 220, "normal": 85, "hard": 0}


@dataclass
class SearchBudget:
    remaining: int
    deadline: float

    def exhausted(self) -> bool:
        return self.remaining <= 0 or time.monotonic() >= self.deadline

    def visit(self) -> bool:
        if self.exhausted():
            return False
        self.remaining -= 1
        return True

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


def _retracts_own_last(game: XiangqiGame, mv: Move) -> bool:
    """是否把己方上一手原路退回（典型「走一步又走回去」）。"""
    for e in reversed(game.history):
        if e.get("color") != game.turn:
            continue
        prev_from = e.get("from")
        prev_to = e.get("to")
        if not prev_from or not prev_to:
            return False
        return [mv.fr, mv.fc] == list(prev_to) and [mv.tr, mv.tc] == list(prev_from)
    return False


def _is_null_retract(game: XiangqiGame, mv: Move) -> bool:
    """无吃子的原路退回——几乎总是废棋（根节点过滤用）。"""
    if not _retracts_own_last(game, mv):
        return False
    return not bool(game.board[mv.tr][mv.tc])


def _order(game: XiangqiGame, moves: list[Move], *, deep: bool = False) -> list[Move]:
    scored: list[tuple[int, Move]] = []
    for mv in moves:
        score = _capture_value(game.board, mv) * 10
        score += 6 - abs(mv.tc - 4)
        if game.board[mv.tr][mv.tc]:
            if deep and not _is_safe_capture(game, mv):
                score -= 350  # 惩罚开局式「炮打马」被反吃
            else:
                score += 80
        # 深排序才探测将军（搜索树里太贵）
        if deep:
            game.play_uci(mv.uci)
            if in_check(game.board, game.turn):
                score += 55
            game.undo()
        # 廉价惩罚原路退回，避免浅搜来回晃
        if _retracts_own_last(game, mv):
            score -= 180 if game.board[mv.tr][mv.tc] else 700
        scored.append((score, mv))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored]


def _quiescence(game: XiangqiGame, alpha: int, beta: int, maximizing: bool, qdepth: int, budget: SearchBudget) -> int:
    if not budget.visit():
        return evaluate_position(game)
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
            best = max(best, _quiescence(game, alpha, beta, False, qdepth - 1, budget))
            game.undo()
            alpha = max(alpha, best)
            if beta <= alpha:
                break
        return best
    best = stand
    for mv in noisy:
        game.play_uci(mv.uci)
        best = min(best, _quiescence(game, alpha, beta, True, qdepth - 1, budget))
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
    budget: SearchBudget,
) -> int:
    if not budget.visit():
        return evaluate_position(game)
    if game.result:
        return evaluate_position(game)
    if depth == 0:
        return _quiescence(game, alpha, beta, maximizing, qdepth=4, budget=budget)

    moves = _order(game, legal_moves(game.board, game.turn))
    if not moves:
        return evaluate_position(game)

    if maximizing:
        best = -10**9
        for mv in moves:
            game.play_uci(mv.uci)
            best = max(best, _search(game, depth - 1, alpha, beta, False, budget))
            game.undo()
            alpha = max(alpha, best)
            if beta <= alpha:
                break
        return best

    best = 10**9
    for mv in moves:
        game.play_uci(mv.uci)
        best = min(best, _search(game, depth - 1, alpha, beta, True, budget))
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


def acceptable_engine_moves(
    candidates: list[tuple[str, int | None]], strength: Strength
) -> list[str]:
    """只从引擎认为不至于明显送子的候选里选，难度决定容差。"""
    if not candidates:
        return []
    best_score = candidates[0][1]
    selected = [candidates[0][0]]
    for uci, score in candidates[1:PIKAFISH_MULTIPV[strength]]:
        if best_score is not None and score is not None:
            if best_score - score <= PIKAFISH_MAX_LOSS_CP[strength]:
                selected.append(uci)
    return selected


def _pick_engine_candidate(candidates: list[tuple[str, int | None]], strength: Strength) -> str | None:
    pool = acceptable_engine_moves(candidates, strength)
    if not pool:
        return None
    if strength == "hard" or len(pool) == 1:
        return pool[0]
    weights = [4, 1] if strength == "normal" else [4, 3, 2, 1]
    return random.choices(pool, weights=weights[:len(pool)], k=1)[0]


def _gifts_undefended_piece(game: XiangqiGame, uci: str) -> bool:
    """无引擎时的最低安全线：避免把马、炮、车直接放到白吃点。"""
    mv = Move.from_uci(uci)
    piece = game.board[mv.fr][mv.fc]
    if PIECE_VALUE.get((piece or "").lower(), 0) < 200:
        return False
    game.play_uci(uci)
    try:
        for reply in legal_moves(game.board, game.turn):
            if (reply.tr, reply.tc) != (mv.tr, mv.tc):
                continue
            game.play_uci(reply.uci)
            try:
                if not any(
                    recapture.tr == mv.tr and recapture.tc == mv.tc
                    for recapture in legal_moves(game.board, game.turn)
                ):
                    return True
            finally:
                game.undo()
    finally:
        game.undo()
    return False


def choose_move_builtin(game: XiangqiGame, *, strength: Strength = "normal") -> str | None:
    book = _book_move(game)
    if book:
        return book

    depth = STRENGTH_DEPTH.get(strength, 5)
    widen = STRENGTH_NODES.get(strength, 64)
    # 根节点用廉价排序即可；深探测会拖到数秒
    ordered = _order(game, legal_moves(game.board, game.turn), deep=False)
    # 有其它着法时，根节点先丢掉无意义原路退回
    non_retract = [mv for mv in ordered if not _is_null_retract(game, mv)]
    pool = non_retract or ordered
    moves = pool[:widen]
    if not moves:
        return None

    # Pikafish 临时不可用时，内建搜索承担最后一道安全线。浅层搜索容易
    # 被“先吃一子”的表面收益诱导，看不到下一手被吃回（例如车换马）。
    # 普通/强档先移除这种没有后续补偿的送大子着；若局面中所有着法都
    # 无法避免损失，则保留原候选，避免把合法着法过滤为空。
    if strength in ("normal", "hard"):
        safe_moves = [mv for mv in moves if not _gifts_undefended_piece(game, mv.uci)]
        if safe_moves:
            moves = safe_moves

    maximizing = game.turn == "red"
    best_score = -10**9 if maximizing else 10**9
    best: list[str] = []
    budget = SearchBudget(
        STRENGTH_NODE_BUDGET.get(strength, 8_000),
        time.monotonic() + STRENGTH_TIME_BUDGET.get(strength, 0.9),
    )

    for mv in moves:
        if best and budget.exhausted():
            break
        game.play_uci(mv.uci)
        score = _search(game, max(0, depth - 1), -10**9, 10**9, not maximizing, budget)
        game.undo()
        # 根着再扣一次，防止同分随机抽到退回着
        if _is_null_retract(game, mv):
            score += -900 if maximizing else 900
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
    # 同分优先不退回
    if len(best) > 1:
        filtered = [u for u in best if not _is_null_retract(game, Move.from_uci(u))]
        if filtered:
            best = filtered
    return random.choice(best) if best else moves[0].uci


def choose_move(
    game: XiangqiGame,
    depth: int | None = None,
    *,
    strength: Strength | None = None,
) -> str | None:
    """引擎选着：有 Pikafish 用引擎，否则用强化内建。"""
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
        from src.xiangqi.engine import candidate_moves_pikafish, pikafish_available

        if pikafish_available():
            candidates = candidate_moves_pikafish(
                game.fen(),
                depth=PIKAFISH_DEPTH[level],
                movetime_ms=PIKAFISH_MOVETIME_MS[level],
                multipv=PIKAFISH_MULTIPV[level],
            )
            mv = _pick_engine_candidate(candidates, level)
            if mv and is_legal(game.board, Move.from_uci(mv), game.turn):
                # 强引擎会把战术、交换和王安全一并计入。最佳着有时必须
                # 原路回防；不能为了“看起来不重复”而用浅搜索覆盖它。
                return mv
    except Exception:
        pass

    return choose_move_builtin(game, strength=level)


AiSide = Literal["engine", "llm", "qwen"]


def opponent_ai(red_ai: AiSide) -> AiSide:
    """AI vs AI：红方选定后，黑方配对（优先 GLM↔千问）。"""
    from src.config import LLM_ENABLED, QWEN_ENABLED

    if red_ai == "llm":
        return "qwen" if QWEN_ENABLED else "engine"
    if red_ai == "qwen":
        return "llm" if LLM_ENABLED else "engine"
    if LLM_ENABLED:
        return "llm"
    if QWEN_ENABLED:
        return "qwen"
    return "engine"


def resolve_ai_side(
    *,
    mode: str,
    turn: str,
    human_color: str = "red",
    red_ai: AiSide = "engine",
) -> AiSide | None:
    """当前应由哪一侧 AI 走；人类回合返回 None。"""
    if mode == "human_vs_human":
        return None
    if mode == "human_vs_ai":
        if turn == human_color:
            return None
        return red_ai if red_ai in ("engine", "llm", "qwen") else "engine"
    if mode == "ai_vs_ai":
        side = red_ai if turn == "red" else opponent_ai(red_ai)
        return side if side in ("engine", "llm", "qwen") else "engine"
    return "engine"


async def choose_move_for_side(
    game: XiangqiGame,
    *,
    ai_side: AiSide = "engine",
    strength: Strength = "normal",
    depth: int | None = None,
) -> dict:
    """统一选着：LLM/千问优先，失败回退引擎。"""
    if ai_side in ("llm", "qwen"):
        try:
            from src.xiangqi.llm_picker import pick_xiangqi_move

            pick = await pick_xiangqi_move(game, which=ai_side, strength=strength)  # type: ignore[arg-type]
            uci = pick.get("uci")
            legal = {mv.uci for mv in legal_moves(game.board, game.turn)}
            if uci and uci in legal:
                # 模型爱「走一步再走回去」：无意义退回直接改用引擎
                if _is_null_retract(game, Move.from_uci(uci)):
                    eng = await asyncio.to_thread(choose_move, game, depth=depth, strength=strength)
                    if eng:
                        return {
                            "uci": eng,
                            "source": "engine_fallback",
                            "reason": f"{ai_side} 选了原路退回，改用引擎",
                            "controller": ai_side,
                        }
                candidates = pick.get("engine_candidates") or []
                acceptable = acceptable_engine_moves(candidates, strength)
                if acceptable and uci not in acceptable:
                    return {
                        "uci": _pick_engine_candidate(candidates, strength),
                        "source": "engine_safety",
                        "reason": f"{ai_side} 候选低于{strength}档安全线，改用引擎",
                        "controller": ai_side,
                    }
                if not acceptable and _gifts_undefended_piece(game, uci):
                    eng = await asyncio.to_thread(choose_move_builtin, game, strength=strength)
                    return {
                        "uci": eng,
                        "source": "engine_safety",
                        "reason": f"{ai_side} 候选会白送大子，改用内建引擎",
                        "controller": ai_side,
                    }
                return {
                    "uci": uci,
                    "source": ai_side,
                    "reason": pick.get("reason") or "",
                    "controller": ai_side,
                }
            fallback_reason = pick.get("reason") or "无效着法"
        except Exception as exc:  # noqa: BLE001
            fallback_reason = f"{type(exc).__name__}: {exc}"
        eng = await asyncio.to_thread(choose_move, game, depth=depth, strength=strength)
        return {
            "uci": eng,
            "source": "engine_fallback",
            "reason": f"{ai_side} 失败({fallback_reason})，回退引擎",
            "controller": ai_side,
        }

    eng = await asyncio.to_thread(choose_move, game, depth=depth, strength=strength)
    return {
        "uci": eng,
        "source": "engine",
        "reason": f"engine · {strength}",
        "controller": "engine",
    }
