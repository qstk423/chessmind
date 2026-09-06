"""规则启发式 Xiangqi Council：攻杀 / 局势 / 风险 + 简易辩论。

无 LLM / Pikafish 时先给出与 ChessCouncil 同结构的可交互分析结果。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.xiangqi.rules import (
    PIECE_NAMES,
    Move,
    XiangqiGame,
    color_of,
    evaluate_material,
    in_check,
    legal_moves,
    move_san,
)

PIECE_VALUE = {"k": 10000, "r": 900, "c": 450, "n": 400, "b": 200, "a": 200, "p": 100}


def _material_for(board, color: str) -> int:
    total = 0
    for r in range(10):
        for c in range(9):
            p = board[r][c]
            if color_of(p) != color:
                continue
            total += PIECE_VALUE.get(p.lower(), 0)
    return total


def _hanging_penalty(game: XiangqiGame, color: str) -> int:
    """粗估：己方被对方一步可吃的无保护子。"""
    enemy = "black" if color == "red" else "red"
    penalty = 0
    enemy_targets = set()
    for mv in legal_moves(game.board, enemy):
        enemy_targets.add((mv.tr, mv.tc))
    for r in range(10):
        for c in range(9):
            p = game.board[r][c]
            if color_of(p) != color or p.lower() == "k":
                continue
            if (r, c) in enemy_targets:
                penalty += PIECE_VALUE.get(p.lower(), 0) // 2
    return penalty


def _mobility(game: XiangqiGame, color: str) -> int:
    return len(legal_moves(game.board, color))


def _center_bonus(move: Move) -> int:
    return max(0, 4 - abs(move.tc - 4)) * 6 + max(0, 3 - abs(move.tr - 4)) * 3


def _score_move(game: XiangqiGame, move: Move, persona: str) -> tuple[int, list[str]]:
    points: list[str] = []
    clone = deepcopy(game)
    captured = clone.board[move.tr][move.tc]
    before_mat = evaluate_material(clone.board)
    entry = clone.play_uci(move.uci)
    after_mat = evaluate_material(clone.board)
    side = entry["color"]
    enemy = "black" if side == "red" else "red"
    gives_check = in_check(clone.board, enemy)
    mate = bool(clone.result and "绝杀" in (clone.result or ""))
    hanging = _hanging_penalty(clone, side)
    mob = _mobility(clone, side) - _mobility(clone, enemy)
    delta = after_mat - before_mat
    if side == "black":
        delta = -delta

    score = 0
    if mate:
        score += 50000
        points.append("此着可绝杀")
    if gives_check:
        score += 220
        points.append("将军")
    if captured:
        score += PIECE_VALUE.get(captured.lower(), 0)
        points.append(f"吃{PIECE_NAMES.get(captured, captured)}")
    score += delta // 3
    score += _center_bonus(move)
    score -= hanging // 3

    if persona == "tactical":
        score += 180 if gives_check else 0
        score += PIECE_VALUE.get((captured or "").lower(), 0) // 2
        score += 80 if mate else 0
        if not points:
            points.append("寻找强制与得子")
    elif persona == "strategic":
        score += mob * 4
        score += _center_bonus(move) * 2
        if move_san and abs(move.tr - 4) <= 2:
            points.append("争夺中路与空间")
        if not captured and not gives_check:
            points.append("改善阵型")
    elif persona == "risk":
        score -= hanging
        score -= 40 if gives_check and hanging > 200 else 0
        score += 30 if not captured else -10
        if hanging > 150:
            points.append("避免留空门子")
        else:
            points.append("优先稳阵与王区安全")
        # 风险官更不愿送子
        if captured and PIECE_VALUE.get(captured.lower(), 0) < 200:
            score -= 20
    else:
        score += (180 if gives_check else 0) // 2
        score += mob * 2

    return score, points[:3]


def _pick_agent(game: XiangqiGame, persona: str, depth_hint: int = 1) -> dict[str, Any]:
    moves = legal_moves(game.board, game.turn)
    if not moves:
        return {
            "recommended_move": "—",
            "uci": None,
            "san": "—",
            "confidence": 0.2,
            "risk": 0.8,
            "evaluation": 0,
            "summary": "无合法着法，局面已结束或困毙。",
            "reasoning_points": [],
            "concerns": ["对局可能已结束"],
        }

    ranked: list[tuple[int, Move, list[str]]] = []
    for mv in moves[:48]:
        score, points = _score_move(game, mv, persona)
        # 浅层展望：对手应着后的物质
        if depth_hint:
            clone = deepcopy(game)
            clone.play_uci(mv.uci)
            if not clone.result:
                reply = legal_moves(clone.board, clone.turn)
                if reply:
                    # 对手吃最大
                    best_cap = max(
                        (PIECE_VALUE.get((clone.board[m.tr][m.tc] or "").lower(), 0) for m in reply[:24]),
                        default=0,
                    )
                    score -= best_cap // (1 if persona != "risk" else 1)
                    if persona == "risk" and best_cap >= 400:
                        points.append("顾虑对手反吃")
        ranked.append((score, mv, points))
    ranked.sort(key=lambda x: x[0], reverse=True)
    best_score, best_mv, points = ranked[0]
    san = move_san(game.board, best_mv)
    mat = evaluate_material(game.board)
    if game.turn == "black":
        mat = -mat
    # 置信：相对第二名差距
    gap = best_score - (ranked[1][0] if len(ranked) > 1 else best_score - 50)
    confidence = max(0.35, min(0.95, 0.45 + gap / 800))
    risk = 0.55 if persona == "tactical" else (0.25 if persona == "risk" else 0.4)
    if in_check(game.board, game.turn):
        risk += 0.15
        points = ["必须先应将", *points][:3]

    titles = {
        "tactical": "攻杀师",
        "strategic": "局势师",
        "risk": "风险官",
        "coach": "教练",
    }
    summaries = {
        "tactical": f"{titles[persona]}看好 {san}，侧重将军、捉子与强制变化。",
        "strategic": f"{titles[persona]}推荐 {san}，看重空间、中路与子力协调。",
        "risk": f"{titles[persona]}倾向 {san}，优先降低漏着与空门风险。",
        "coach": f"教练综合建议走 {san}。",
    }
    concerns = []
    if in_check(game.board, game.turn):
        concerns.append("己方正在被将军")
    if _hanging_penalty(game, game.turn) > 200:
        concerns.append("有子可能被对方吃掉")

    return {
        "role": persona,
        "title": titles.get(persona, persona),
        "recommended_move": san,
        "uci": best_mv.uci,
        "san": san,
        "confidence": round(confidence, 2),
        "risk": round(min(0.95, risk), 2),
        "evaluation": mat,
        "summary": summaries.get(persona, summaries["coach"]),
        "reasoning_points": points or ["按启发式排序"],
        "concerns": concerns,
        "parse_ok": True,
    }


def _eval_probs(game: XiangqiGame) -> dict[str, Any]:
    mat = evaluate_material(game.board)
    # 映射到红方胜率观感
    raw = 50 + max(-40, min(40, mat / 40))
    if in_check(game.board, "black"):
        raw += 4
    if in_check(game.board, "red"):
        raw -= 4
    red = max(8, min(92, raw))
    black = 100 - red
    label = "均势"
    if red >= 62:
        label = "红优"
    elif red <= 38:
        label = "黑优"
    elif abs(red - 50) < 6:
        label = "均势"
    else:
        label = "略优·红" if red > 50 else "略优·黑"
    return {
        "red_pct": round(red),
        "black_pct": round(black),
        "material": mat,
        "label": label,
    }


def analyze_position(game: XiangqiGame) -> dict[str, Any]:
    if game.result:
        return {
            "fen": game.fen(),
            "turn": game.turn,
            "eval": _eval_probs(game),
            "agents": {},
            "disagreement": {"disagreement_score": 0, "badge": "终局", "recommended_moves": {}},
            "debate": {"triggered": False, "rounds": []},
            "verdict": {
                "recommended_move": "—",
                "summary": game.result,
                "confidence": 1.0,
            },
            "move_class": "终局",
        }

    tactical = _pick_agent(game, "tactical")
    strategic = _pick_agent(game, "strategic")
    risk = _pick_agent(game, "risk")

    moves = {
        "tactical": tactical["recommended_move"],
        "strategic": strategic["recommended_move"],
        "risk": risk["recommended_move"],
    }
    ucis = {
        "tactical": tactical["uci"],
        "strategic": strategic["uci"],
        "risk": risk["uci"],
    }
    unique = {m for m in moves.values() if m and m != "—"}
    score = 0.0 if len(unique) <= 1 else (0.55 if len(unique) == 2 else 0.85)
    badge = "一致" if score < 0.35 else ("分歧" if score < 0.7 else "激烈争议")

    # 教练：多数票，争议时偏风险官
    vote: dict[str, int] = {}
    for key in ("tactical", "strategic", "risk"):
        m = moves[key]
        vote[m] = vote.get(m, 0) + (2 if key == "risk" and score >= 0.55 else 1)
    winner = max(vote.items(), key=lambda x: x[1])[0]
    winner_uci = next(ucis[k] for k, v in moves.items() if v == winner)
    coach = {
        "role": "coach",
        "title": "教练",
        "recommended_move": winner,
        "uci": winner_uci,
        "san": winner,
        "confidence": round(0.5 + (1 - score) * 0.35, 2),
        "risk": risk["risk"],
        "evaluation": tactical["evaluation"],
        "summary": (
            f"三位分析师{'意见一致' if score < 0.35 else '存在分歧'}。"
            f"教练采纳 {winner}。"
            + (" 建议先看辩论页。" if score >= 0.55 else "")
        ),
        "reasoning_points": [
            f"攻杀师：{moves['tactical']}",
            f"局势师：{moves['strategic']}",
            f"风险官：{moves['risk']}",
        ],
        "concerns": risk.get("concerns") or [],
        "parse_ok": True,
        "takeaway": f"本步先记住：优先考虑 {winner}。",
    }

    debate_rounds = []
    triggered = score >= 0.55
    if triggered:
        debate_rounds = [
            {
                "speaker": "攻杀师",
                "role": "tactical",
                "text": f"应当走 {moves['tactical']}。不主动施压，对手会先把火力组织起来。",
            },
            {
                "speaker": "局势师",
                "role": "strategic",
                "text": f"我更看 {moves['strategic']}。先抢空间和中路，比一时得子更稳。",
            },
            {
                "speaker": "风险官",
                "role": "risk",
                "text": f"反对冒进。{moves['risk']} 更能保住阵型，避免被反将或丢子。",
            },
            {
                "speaker": "仲裁",
                "role": "arbiter",
                "text": f"综合争议度 {int(score * 100)}%，本步裁决为 {winner}。",
            },
        ]

    verdict = {
        "recommended_move": winner,
        "uci": winner_uci,
        "confidence": coach["confidence"],
        "summary": coach["summary"],
    }

    ev = _eval_probs(game)
    move_class = "待走"
    if in_check(game.board, game.turn):
        move_class = "应将"
    elif score >= 0.7:
        move_class = "分歧局"
    else:
        move_class = ev["label"]

    return {
        "fen": game.fen(),
        "turn": game.turn,
        "eval": ev,
        "agents": {
            "tactical": tactical,
            "strategic": strategic,
            "risk": risk,
            "coach": coach,
        },
        "disagreement": {
            "disagreement_score": score,
            "badge": badge,
            "recommended_moves": moves,
            "trigger_debate": triggered,
        },
        "debate": {"triggered": triggered, "rounds": debate_rounds},
        "verdict": verdict,
        "move_class": move_class,
        "engine": "builtin_heuristics",
    }
