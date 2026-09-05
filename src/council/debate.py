"""辩论与仲裁：高分歧时交叉质询，再由 Arbiter + 引擎落地。"""
from __future__ import annotations

from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.schema import (
    AgentOpinion,
    JSON_OUTPUT_RULES,
    normalize_move_token,
)
from src.agents.risk import RiskAgent
from src.agents.strategic import StrategicAgent
from src.agents.tactical import TacticalAgent


ARBITER_PROMPT = f"""你是 ChessCouncil 的仲裁官（agent id: arbiter）。

你将收到战术/战略/风险三方意见、辩论记录，以及 Stockfish 的客观计算。
必须以引擎事实为最高优先级解决矛盾，给出最终推荐着法与理由。

{JSON_OUTPUT_RULES}

其中 "agent" 字段必须为 "arbiter"。
recommended_move 必须尽量与引擎 PV 首着或明显更优着一致；若采纳非引擎着法，须在 concerns 说明风险。
使用中文。"""


class ArbiterAgent(BaseAgent):
    agent_id = "arbiter"

    def __init__(self, client, model):
        super().__init__("仲裁官", ARBITER_PROMPT, client, model)


async def run_debate(
    *,
    tactical_agent: TacticalAgent,
    strategic_agent: StrategicAgent,
    risk_agent: RiskAgent,
    arbiter: ArbiterAgent,
    fen: str,
    history: list[str],
    grounding: str,
    stockfish_info: dict[str, Any],
    opinions: dict[str, AgentOpinion],
) -> dict[str, Any]:
    """
    轻量辩论：
    1) 风险方发起质询
    2) 战术/战略各答辩一次
    3) 仲裁官结合引擎输出最终 JSON 意见
    """
    tac = opinions["tactical"]
    strat = opinions["strategic"]
    risk = opinions["risk"]
    pv = stockfish_info.get("pv") or []
    engine_hint = f"Stockfish score_cp={stockfish_info.get('score_cp')}, pv={pv}, mate={stockfish_info.get('mate_in')}"

    challenge_user = f"""局面 FEN：{fen}
历史：{' '.join(history) if history else '开局'}
{grounding}
{engine_hint}

战术意见：{tac.to_dict()}
战略意见：{strat.to_dict()}
你的风险意见：{risk.to_dict()}

请用中文提出不超过 5 句的交叉质询：分别质疑战术与战略方案中最危险的一点，并给出你主张的更稳妥着法。"""

    challenge = await risk_agent.chat_raw(
        "你是风险审查员，正在辩论中发起质询。只输出质询正文。",
        challenge_user,
        agent_label="风险质询",
        max_tokens=350,
    )

    reply_tac = await tactical_agent.chat_raw(
        "你是战术分析师，正在回应风险质询。简短辩护或修正观点，中文，不超过 5 句。",
        f"质询内容：\n{challenge}\n\n你的原意见：{tac.summary}\n推荐：{tac.recommended_move}\n引擎：{engine_hint}",
        agent_label="战术答辩",
        max_tokens=280,
    )

    reply_strat = await strategic_agent.chat_raw(
        "你是战略分析师，正在回应风险质询。简短辩护或修正观点，中文，不超过 5 句。",
        f"质询内容：\n{challenge}\n\n你的原意见：{strat.summary}\n推荐：{strat.recommended_move}\n引擎：{engine_hint}",
        agent_label="战略答辩",
        max_tokens=280,
    )

    arbiter_context = f"""{grounding}
{engine_hint}

【战术意见】{tac.to_dict()}
【战略意见】{strat.to_dict()}
【风险意见】{risk.to_dict()}

【风险质询】{challenge}
【战术答辩】{reply_tac}
【战略答辩】{reply_strat}
"""
    verdict = await arbiter.analyze_structured(fen, history, arbiter_context, max_tokens=650)

    # 若仲裁无着法，回退引擎 PV 首着（SAN）
    if not verdict.recommended_move and pv:
        verdict.recommended_move = normalize_move_token(str(pv[0]))
        if not verdict.fallback_reason:
            verdict.fallback_reason = "arbiter_fallback_engine_pv"

    return {
        "triggered": True,
        "rounds": [
            {"speaker": "risk", "role": "challenge", "text": challenge},
            {"speaker": "tactical", "role": "rebuttal", "text": reply_tac},
            {"speaker": "strategic", "role": "rebuttal", "text": reply_strat},
        ],
        "verdict": verdict.to_dict(),
    }


def consensus_verdict(opinions: dict[str, AgentOpinion], stockfish_info: dict[str, Any]) -> AgentOpinion:
    """低分歧时不辩论：用多数着法 + 引擎对齐生成简易裁决。"""
    tac = opinions["tactical"]
    strat = opinions["strategic"]
    risk = opinions["risk"]
    moves = [normalize_move_token(m) for m in (tac.recommended_move, strat.recommended_move, risk.recommended_move)]
    moves = [m for m in moves if m]
    final = None
    if moves:
        # 多数投票
        counts: dict[str, int] = {}
        for m in moves:
            counts[m] = counts.get(m, 0) + 1
        final = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[0][0]
    pv = stockfish_info.get("pv") or []
    if not final and pv:
        final = normalize_move_token(str(pv[0]))

    conf = round((tac.confidence + strat.confidence + risk.confidence) / 3, 3)
    risk_avg = round((tac.risk + strat.risk + risk.risk) / 3, 3)
    ev = stockfish_info.get("score_cp")
    evaluation = round((ev / 100.0), 2) if isinstance(ev, (int, float)) else round(
        (tac.evaluation + strat.evaluation + risk.evaluation) / 3, 2
    )
    summary = (
        f"三方意见基本一致，综合推荐 {final or '（参考引擎）'}。"
        f"战术：{tac.summary[:60]} 战略：{strat.summary[:60]}"
    )
    return AgentOpinion(
        agent="arbiter",
        recommended_move=final,
        alternative_moves=[],
        confidence=conf,
        evaluation=evaluation,
        risk=risk_avg,
        summary=summary,
        reasoning_points=[
            f"战术推荐 {tac.recommended_move}",
            f"战略推荐 {strat.recommended_move}",
            f"风险推荐 {risk.recommended_move}",
            f"引擎 PV：{', '.join(map(str, pv[:3]))}",
        ],
        concerns=list({*(tac.concerns[:1]), *(risk.concerns[:1])}),
        parse_ok=True,
    )
