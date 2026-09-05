"""分歧检测：综合着法/评估/风险/置信度，输出可解释的 disagreement_score。"""
from __future__ import annotations

from typing import Any

from src.agents.schema import AgentOpinion, normalize_move_token


def _norm_move(m: str | None) -> str | None:
    return normalize_move_token(m)


def compute_disagreement(
    tactical: AgentOpinion,
    strategic: AgentOpinion,
    risk: AgentOpinion,
) -> dict[str, Any]:
    """
    加权分歧分数 0~1：
    - move: 0.45
    - evaluation: 0.20
    - risk: 0.20
    - confidence / attitude: 0.15
    """
    agents = [tactical, strategic, risk]
    moves = [_norm_move(a.recommended_move) for a in agents]
    present = [m for m in moves if m]
    unique = set(present)

    if len(present) <= 1:
        move_score = 0.0
    elif len(unique) == 1:
        move_score = 0.0
    elif len(unique) == 2:
        move_score = 0.55
    else:
        move_score = 1.0

    # 若 Risk 与另两者推荐完全不同，加重着法分歧
    tac_m, strat_m, risk_m = moves
    if risk_m and tac_m and strat_m and risk_m != tac_m and risk_m != strat_m:
        move_score = max(move_score, 0.75)
    if tac_m and strat_m and tac_m != strat_m:
        move_score = max(move_score, 0.6)

    evals = [a.evaluation for a in agents]
    eval_spread = min(1.0, abs(max(evals) - min(evals)) / 3.0)  # 3 兵视为满分分歧

    risks = [a.risk for a in agents]
    risk_spread = abs(max(risks) - min(risks))

    confs = [a.confidence for a in agents]
    conf_spread = abs(max(confs) - min(confs))

    # 态度相反：Risk 对他人推荐着法给出高 risk 且自己 confidence 高
    attitude = 0.0
    others = [tac_m, strat_m]
    if risk_m and any(o and o != risk_m for o in others):
        attitude = min(1.0, 0.4 + risk.confidence * 0.3 + risk.risk * 0.3)
    attitude_component = max(conf_spread, attitude * 0.7)

    score = (
        0.45 * move_score
        + 0.20 * eval_spread
        + 0.20 * risk_spread
        + 0.15 * attitude_component
    )
    score = round(max(0.0, min(1.0, score)), 4)

    if score < 0.25:
        level = "consensus"
        label = "意见基本一致"
        badge = "共识"
    elif score < 0.5:
        level = "mild"
        label = "存在轻微差异"
        badge = "低争议"
    elif score < 0.75:
        level = "clear"
        label = "明显分歧"
        badge = "高争议"
    else:
        level = "hot"
        label = "高度争议"
        badge = "🔥 高争议局面"

    return {
        "disagreement_score": score,
        "consensus_score": round(1.0 - score, 4),
        "level": level,
        "label": label,
        "badge": badge,
        "components": {
            "move": round(move_score, 4),
            "evaluation": round(eval_spread, 4),
            "risk": round(risk_spread, 4),
            "confidence_attitude": round(attitude_component, 4),
        },
        "recommended_moves": {
            "tactical": tac_m,
            "strategic": strat_m,
            "risk": risk_m,
        },
        "trigger_debate": score >= 0.5,
    }
