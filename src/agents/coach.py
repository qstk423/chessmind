"""🎓 AI 教练 —— 按用户水平解释，不直接参与裁决投票"""
from __future__ import annotations

from typing import Any, Literal

from src.agents.base_agent import BaseAgent
from src.agents.schema import JSON_OUTPUT_RULES, AgentOpinion

CoachLevel = Literal["beginner", "intermediate", "advanced"]

LEVEL_HINT = {
    "beginner": "面向初学者：少用术语，用生活化比喻，说明「为什么这样想」；避免 calculation 等英文术语。",
    "intermediate": "面向中级：可使用常见战术/战略术语（牵制、弱格、半开放线等），点出关键思路。",
    "advanced": "面向高级：可讨论 calculation、candidate moves、positional compensation、引擎评估差异。",
}


COACH_PROMPT = f"""你是 ChessCouncil 的 AI 教练（agent id: coach）。图标：🎓

你不参与最终棋步投票。你的任务是把其他 Agent、辩论过程与 Stockfish 结论，
翻译成指定水平玩家能听懂的讲解。

{JSON_OUTPUT_RULES}

其中 "agent" 字段必须为 "coach"。
recommended_move 应与最终裁决着法一致（若已给出）。
summary 必须是面向人类的讲解正文（按指定水平）。
reasoning_points 写 2~5 条学习要点。
concerns 写玩家容易忽略的陷阱。"""


class CoachAgent(BaseAgent):
    agent_id = "coach"

    def __init__(self, client, model):
        super().__init__("AI教练", COACH_PROMPT, client, model)

    async def explain(
        self,
        *,
        fen: str,
        move_history: list[str],
        grounding: str,
        stockfish_info: dict[str, Any],
        move_class: str,
        level: CoachLevel,
        council_snapshot: str,
        final_move: str | None,
    ) -> AgentOpinion:
        hint = LEVEL_HINT.get(level, LEVEL_HINT["intermediate"])
        mate = ""
        if stockfish_info.get("is_mate"):
            mate = f"，杀棋 {stockfish_info.get('mate_in')}"
        extra = f"""用户水平：{level}
讲解要求：{hint}

引擎：{stockfish_info.get('score_cp')} cp{mate}；白胜率 {stockfish_info.get('win_prob_white')}；PV {stockfish_info.get('pv')}
走子分类：{move_class}
最终裁决着法：{final_move or '（未定）'}

=== Council 材料 ===
{council_snapshot}

{grounding}
"""
        opinion = await self.analyze_structured(fen, move_history, extra)
        if opinion.recommended_move is None and final_move:
            opinion.recommended_move = final_move
        return opinion
