"""赛后复盘报告：从本局逐步 Council 记录生成结构化复盘。"""
from __future__ import annotations

from typing import Any


CLASS_SCORE = {
    "brilliant": 3,
    "great": 2,
    "good": 1,
    "inaccuracy": -1,
    "mistake": -2,
    "blunder": -3,
}


def build_review(move_records: list[dict[str, Any]], *, game_result: str | None, pgn: str) -> dict[str, Any]:
    """根据逐步分析结果生成复盘摘要（不调用 LLM，确定性、可演示）。"""
    if not move_records:
        return {
            "title": "本局复盘",
            "result": game_result or "未开始",
            "total_moves": 0,
            "highlights": [],
            "debates": [],
            "classification_counts": {},
            "avg_disagreement": 0.0,
            "narrative": ["本局尚无走子记录。"],
            "pgn": pgn,
        }

    counts: dict[str, int] = {}
    highlights = []
    debates = []
    dg_scores = []

    for rec in move_records:
        cls = (rec.get("evaluation") or {}).get("classification") or "good"
        counts[cls] = counts.get(cls, 0) + 1
        council = ((rec.get("analysis") or {}).get("council")) or {}
        dg = council.get("disagreement") or {}
        score = float(dg.get("disagreement_score") or 0)
        dg_scores.append(score)
        move = rec.get("move") or {}
        entry = {
            "number": move.get("number"),
            "san": move.get("san"),
            "classification": cls,
            "disagreement_score": score,
            "badge": dg.get("badge"),
            "verdict": (council.get("verdict") or {}).get("recommended_move"),
            "coach": ((council.get("agents") or {}).get("coach") or {}).get("summary"),
        }
        if cls in ("brilliant", "great", "mistake", "blunder") or score >= 0.5:
            highlights.append(entry)
        if (council.get("debate") or {}).get("triggered"):
            debates.append({
                **entry,
                "rounds": len((council.get("debate") or {}).get("rounds") or []),
                "verdict_summary": (council.get("verdict") or {}).get("summary"),
            })

    avg_dg = round(sum(dg_scores) / len(dg_scores), 4) if dg_scores else 0.0
    # 精彩度：高争议 + 极端分类
    highlights = sorted(
        highlights,
        key=lambda h: (
            1 if (h.get("disagreement_score") or 0) >= 0.5 else 0,
            abs(CLASS_SCORE.get(h.get("classification") or "good", 0)),
            h.get("disagreement_score") or 0,
        ),
        reverse=True,
    )[:8]

    narrative = [
        f"本局共 {len(move_records)} 步，结果：{game_result or '进行中/未知'}。",
        f"平均 AI 争议度 {round(avg_dg * 100)}%；触发辩论 {len(debates)} 次。",
    ]
    if counts.get("brilliant") or counts.get("great"):
        narrative.append(
            f"亮点着法：妙手 {counts.get('brilliant', 0)}、好棋 {counts.get('great', 0)}。"
        )
    if counts.get("mistake") or counts.get("blunder"):
        narrative.append(
            f"需警惕：漏着 {counts.get('mistake', 0)}、大漏 {counts.get('blunder', 0)}。"
        )
    if debates:
        d0 = debates[0]
        narrative.append(
            f"最高戏剧性辩论出现在第 {d0.get('number')} 步 {d0.get('san')}，"
            f"仲裁推荐 {d0.get('verdict') or '—'}。"
        )
    elif highlights:
        h0 = highlights[0]
        narrative.append(
            f"关键局面：第 {h0.get('number')} 步 {h0.get('san')}（{h0.get('classification')}）。"
        )

    return {
        "title": "ChessCouncil 赛后复盘",
        "result": game_result or "未知",
        "total_moves": len(move_records),
        "classification_counts": counts,
        "avg_disagreement": avg_dg,
        "debate_count": len(debates),
        "highlights": highlights,
        "debates": debates,
        "narrative": narrative,
        "pgn": pgn,
    }
