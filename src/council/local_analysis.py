"""国际象棋本地快评：用规则事实和 Stockfish 结果即时生成 Council。"""
from __future__ import annotations

from typing import Any

import chess

from src.agents.schema import AgentOpinion
from src.council.disagreement import compute_disagreement


PIECE_VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

CLASS_LABEL = {
    "brilliant": "妙手",
    "great": "好棋",
    "good": "正常着法",
    "inaccuracy": "缓着",
    "mistake": "漏着",
    "blunder": "大漏",
    "position": "当前局面",
}


def _move_facts(board: chess.Board, move: chess.Move) -> dict[str, Any]:
    san = board.san(move)
    captured = board.piece_at(move.to_square)
    if board.is_en_passant(move):
        captured = chess.Piece(chess.PAWN, not board.turn)
    mover = board.piece_at(move.from_square)
    before_turn = board.turn
    after = board.copy(stack=False)
    after.push(move)
    gives_check = after.is_check()
    is_mate = after.is_checkmate()
    # 对方下一手能直接吃掉落点，视作有战术风险（王不参与该提示）。
    capturable = False
    if mover and mover.piece_type != chess.KING:
        capturable = any(
            reply.to_square == move.to_square and after.is_capture(reply)
            for reply in after.legal_moves
        )
    center = chess.square_file(move.to_square) in (3, 4) and chess.square_rank(move.to_square) in (3, 4)
    develops = bool(
        mover
        and mover.piece_type in (chess.KNIGHT, chess.BISHOP)
        and chess.square_rank(move.from_square) == (0 if before_turn == chess.WHITE else 7)
    )
    return {
        "move": move,
        "san": san,
        "capture": captured,
        "capture_value": PIECE_VALUE.get(captured.piece_type, 0) if captured else 0,
        "mover_value": PIECE_VALUE.get(mover.piece_type, 0) if mover else 0,
        "check": gives_check,
        "mate": is_mate,
        "capturable": capturable,
        "center": center,
        "develops": develops,
        "castle": board.is_castling(move),
        "promotion": move.promotion is not None,
    }


def _engine_move(board: chess.Board, engine_eval: dict[str, Any]) -> chess.Move | None:
    pv = engine_eval.get("pv") or []
    if not pv:
        return None
    try:
        return board.parse_san(str(pv[0]))
    except (ValueError, AssertionError):
        return None


def _rank_tactical(facts: dict[str, Any]) -> float:
    return (
        (100_000 if facts["mate"] else 0)
        + (600 if facts["check"] else 0)
        + facts["capture_value"] * 140
        + (80 if facts["promotion"] else 0)
        - (facts["mover_value"] * 45 if facts["capturable"] else 0)
    )


def _rank_strategic(facts: dict[str, Any]) -> float:
    return (
        facts["capture_value"] * 45
        + (150 if facts["castle"] else 0)
        + (90 if facts["develops"] else 0)
        + (55 if facts["center"] else 0)
        + (35 if facts["check"] else 0)
        - (facts["mover_value"] * 35 if facts["capturable"] else 0)
    )


def _rank_risk(facts: dict[str, Any]) -> float:
    return (
        facts["capture_value"] * 55
        + (100 if facts["castle"] else 0)
        + (55 if facts["develops"] else 0)
        + (30 if facts["center"] else 0)
        - (facts["mover_value"] * 180 if facts["capturable"] else 0)
    )


def _best_by(board: chess.Board, ranker) -> dict[str, Any] | None:
    facts = [_move_facts(board, move) for move in board.legal_moves]
    return max(facts, key=ranker) if facts else None


def _evaluation_pawns(engine_eval: dict[str, Any]) -> float:
    score = engine_eval.get("score_cp")
    return round(float(score) / 100.0, 2) if isinstance(score, (int, float)) else 0.0


def _opinion(
    role: str,
    facts: dict[str, Any] | None,
    *,
    evaluation: float,
    summary: str,
    points: list[str],
    risk: float,
    confidence: float,
) -> AgentOpinion:
    return AgentOpinion(
        agent=role,
        recommended_move=facts["san"] if facts else None,
        confidence=confidence,
        evaluation=evaluation,
        risk=risk,
        summary=summary,
        reasoning_points=points[:5],
        concerns=["落点可能被对方立即攻击"] if facts and facts["capturable"] else [],
        parse_ok=True,
        fallback_reason=None,
    )


def build_local_council(
    *,
    fen: str,
    engine_eval: dict[str, Any],
    move_class: str,
    coach_level: str = "intermediate",
) -> dict[str, Any]:
    """生成与 LLM Council 同结构的确定性快评，全程不访问网络。"""
    board = chess.Board(fen)
    evaluation = _evaluation_pawns(engine_eval)
    engine = _engine_move(board, engine_eval)
    engine_facts = _move_facts(board, engine) if engine else None
    tactical = engine_facts or _best_by(board, _rank_tactical)
    strategic = engine_facts or _best_by(board, _rank_strategic)
    risk_pick = _best_by(board, _rank_risk) or engine_facts

    tac_points = ["优先参考 Stockfish 主变化"] if engine_facts else ["按将军、吃子与强制性排序"]
    if tactical and tactical["check"]:
        tac_points.append("候选着形成将军")
    if tactical and tactical["capture"]:
        tac_points.append(f"可获得约 {tactical['capture_value']} 兵价值子力")
    if tactical and tactical["mate"]:
        tac_points.insert(0, "存在一步将杀")

    strat_points = ["以引擎首选为底座，兼顾发展和中心"] if engine_facts else ["改善子力协调与中心控制"]
    if strategic and strategic["develops"]:
        strat_points.append("完成轻子发展")
    if strategic and strategic["center"]:
        strat_points.append("加强中心控制")
    if strategic and strategic["castle"]:
        strat_points.append("通过易位改善王安全")

    risk_points = ["检查落点是否会被立即吃回", "优先避免无补偿送子"]
    if risk_pick and not risk_pick["capturable"]:
        risk_points.append("该候选落点暂未发现直接反吃")
    if board.is_check():
        risk_points.insert(0, "当前必须先解除将军")

    opinions = {
        "tactical": _opinion(
            "tactical", tactical, evaluation=evaluation,
            summary=f"战术上优先考虑 {tactical['san'] if tactical else '—'}，先看强制变化与子力得失。",
            points=tac_points, risk=0.38 if tactical and not tactical["capturable"] else 0.68,
            confidence=0.86 if engine_facts else 0.68,
        ),
        "strategic": _opinion(
            "strategic", strategic, evaluation=evaluation,
            summary=f"战略上倾向 {strategic['san'] if strategic else '—'}，重点保持发展、中心与王安全。",
            points=strat_points, risk=0.32 if strategic and not strategic["capturable"] else 0.58,
            confidence=0.82 if engine_facts else 0.64,
        ),
        "risk": _opinion(
            "risk", risk_pick, evaluation=evaluation,
            summary=f"风险审查建议 {risk_pick['san'] if risk_pick else '—'}，优先规避立即反吃和无补偿失子。",
            points=risk_points, risk=0.2 if risk_pick and not risk_pick["capturable"] else 0.7,
            confidence=0.72,
        ),
    }
    disagreement = compute_disagreement(
        opinions["tactical"], opinions["strategic"], opinions["risk"]
    )
    disagreement["trigger_debate"] = False
    disagreement["fast_mode"] = True
    disagreement["local_heuristic"] = True

    engine_san = engine_facts["san"] if engine_facts else None
    final_move = engine_san or opinions["tactical"].recommended_move
    verdict = AgentOpinion(
        agent="arbiter",
        recommended_move=final_move,
        confidence=0.88 if engine_san else 0.68,
        evaluation=evaluation,
        risk=round(sum(op.risk for op in opinions.values()) / 3, 2),
        summary=f"本地快评综合推荐 {final_move or '—'}；客观依据以 Stockfish 计算为准。",
        reasoning_points=[
            f"Stockfish 评估 {evaluation:+.2f} 兵",
            *( [f"引擎主变化首着：{engine_san}"] if engine_san else ["引擎未返回主变化，采用规则候选"] ),
        ],
        parse_ok=True,
    )
    class_label = CLASS_LABEL.get(move_class, move_class)
    win_white = round(float(engine_eval.get("win_prob_white", 0.5)) * 100)
    level_note = {
        "beginner": "先记住：落子前检查将军、吃子和对方反击。",
        "advanced": "结合引擎主变化继续验证候选着的强制变化。",
    }.get(coach_level, "先看对手的直接威胁，再比较候选着的长期价值。")
    coach = AgentOpinion(
        agent="coach",
        recommended_move=final_move,
        confidence=verdict.confidence,
        evaluation=evaluation,
        risk=verdict.risk,
        summary=f"本步属于{class_label}，当前白方胜率估计约 {win_white}%。下一步可优先考虑 {final_move or '稳健发展'}。",
        reasoning_points=[level_note, *verdict.reasoning_points],
        concerns=list(opinions["risk"].concerns),
        parse_ok=True,
    )
    opinions["coach"] = coach

    return {
        "tactical": opinions["tactical"].summary,
        "strategic": opinions["strategic"].summary,
        "pattern": opinions["risk"].summary,
        "summary": coach.summary,
        "council": {
            "agents": {name: opinion.to_dict() for name, opinion in opinions.items()},
            "disagreement": disagreement,
            "debate": {
                "triggered": False,
                "rounds": [],
                "verdict": verdict.to_dict(),
                "skipped_reason": "local_fast_mode",
            },
            "verdict": verdict.to_dict(),
            "coach_level": coach_level,
            "analysis_mode": "fast",
            "analysis_source": "local_heuristic",
        },
    }
