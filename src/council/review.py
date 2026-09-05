"""赛后复盘报告：从本局逐步 Council 记录生成结构化复盘。"""
from __future__ import annotations

from typing import Any

from src.board.move_evaluator import MoveEvaluator


CLASS_SCORE = {
    "brilliant": 3,
    "great": 2,
    "good": 1,
    "inaccuracy": -1,
    "mistake": -2,
    "blunder": -3,
}


def _white_win_pct(after: dict[str, Any] | None) -> float | None:
    """从引擎 after 评估得到白方胜率百分比。"""
    if not after:
        return None
    wp = after.get("win_prob_white")
    if isinstance(wp, (int, float)):
        return round(float(wp) * 100.0, 1)
    cp = after.get("score_cp")
    if isinstance(cp, (int, float)):
        return round(MoveEvaluator._cp_to_win_prob(int(cp)) * 100.0, 1)
    return None


def build_eval_curve(move_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    白方优势曲线（稀疏关键点）：advantage = 白胜率% - 50。
    >0 白优（零线上方），<0 黑优（零线下方）。
    不逐手取样，只保留开局、终局与跨度较大的转折点，便于看整体趋势。
    """
    start_fen = None
    for rec in move_records:
        move = rec.get("move") or {}
        if move.get("san") in (None, "", "局面分析", "终局复盘") or rec.get("position_only"):
            continue
        start_fen = rec.get("fen_before")
        break

    points: list[dict[str, Any]] = [
        {
            "ply": 0,
            "san": "开局",
            "white_win": 50.0,
            "black_win": 50.0,
            "advantage": 0.0,
            "classification": None,
            "fen": start_fen,
        }
    ]
    for rec in move_records:
        if rec.get("position_only"):
            continue
        move = rec.get("move") or {}
        san = move.get("san")
        if san in (None, "", "局面分析", "终局复盘"):
            continue
        after = (rec.get("evaluation") or {}).get("after") or {}
        white_win = _white_win_pct(after)
        if white_win is None:
            continue
        points.append(
            {
                "ply": move.get("number") or len(points),
                "san": san,
                "white_win": white_win,
                "black_win": round(100.0 - white_win, 1),
                "advantage": round(white_win - 50.0, 1),
                "classification": (rec.get("evaluation") or {}).get("classification"),
                "fen": rec.get("fen"),
            }
        )
    return _thin_eval_curve(points)


def _thin_eval_curve(
    points: list[dict[str, Any]],
    *,
    max_points: int = 7,
    min_swing: float = 8.0,
    min_ply_gap: int = 3,
) -> list[dict[str, Any]]:
    """从逐步点中抽稀疏关键点：大波动 / 漏着妙手 / 开终局。"""
    if len(points) <= max_points:
        return points

    important = {"brilliant", "great", "mistake", "blunder"}
    kept_idx = [0]

    for i in range(1, len(points) - 1):
        p = points[i]
        last = points[kept_idx[-1]]
        swing = abs(float(p["advantage"]) - float(last["advantage"]))
        ply_gap = int(p.get("ply") or i) - int(last.get("ply") or 0)
        is_key = p.get("classification") in important
        if ply_gap >= min_ply_gap and (swing >= min_swing or (is_key and swing >= 4.0)):
            kept_idx.append(i)

    last_i = len(points) - 1
    if kept_idx[-1] != last_i:
        kept_idx.append(last_i)

    # 过密：保留开终局，中间按波动幅度取最显著的若干点
    if len(kept_idx) > max_points:
        mid = kept_idx[1:-1]
        scored = sorted(
            (
                abs(float(points[i]["advantage"]) - float(points[max(0, i - 1)]["advantage"]))
                + abs(float(points[i]["advantage"])) * 0.25,
                i,
            )
            for i in mid
        )
        need = max_points - 2
        mid_keep = sorted(i for _, i in scored[-need:])
        kept_idx = [0, *mid_keep, last_i]

    # 过稀：等距补点，长对局也能看出走势
    if len(kept_idx) < min(4, max_points) and len(points) >= 4:
        target = min(max_points, 5)
        even = {
            int(round(j * (len(points) - 1) / (target - 1)))
            for j in range(target)
        }
        kept_idx = sorted(set(kept_idx) | even)[:max_points]
        if kept_idx[-1] != last_i:
            kept_idx = sorted(set(kept_idx[:-1] if len(kept_idx) >= max_points else kept_idx) | {0, last_i})
            if len(kept_idx) > max_points:
                mid = kept_idx[1:-1]
                step = len(mid) / max(1, max_points - 2)
                pick = [mid[min(len(mid) - 1, int(k * step))] for k in range(max_points - 2)]
                kept_idx = [0, *pick, last_i]

    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for i in kept_idx:
        if i in seen or i < 0 or i >= len(points):
            continue
        seen.add(i)
        out.append(points[i])
    return out


CLASS_ACCURACY = {
    "brilliant": 100.0,
    "great": 95.0,
    "best": 100.0,
    "good": 80.0,
    "book": 90.0,
    "inaccuracy": 50.0,
    "mistake": 20.0,
    "blunder": 0.0,
}


def compute_accuracy(move_records: list[dict[str, Any]]) -> dict[str, Any]:
    """按走子分类估算准确率（0–100），分白/黑与总评。"""
    white: list[float] = []
    black: list[float] = []
    for rec in move_records:
        if rec.get("position_only"):
            continue
        move = rec.get("move") or {}
        san = move.get("san")
        if san in (None, "", "局面分析", "终局复盘"):
            continue
        cls = (rec.get("evaluation") or {}).get("classification") or "good"
        if cls == "position":
            continue
        pts = float(CLASS_ACCURACY.get(cls, 70.0))
        fen_before = rec.get("fen_before") or ""
        parts = fen_before.split()
        if len(parts) > 1 and parts[1] in ("w", "b"):
            mover = parts[1]
        else:
            num = int(move.get("number") or 0)
            mover = "w" if num % 2 == 1 else "b"
        (white if mover == "w" else black).append(pts)

    def _avg(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 1) if xs else None

    overall_list = white + black
    return {
        "overall": _avg(overall_list),
        "white": _avg(white),
        "black": _avg(black),
        "white_moves": len(white),
        "black_moves": len(black),
        "scale": "0-100",
        "note": "由引擎走子分类换算（妙手/好棋/缓着/漏着/大漏）",
    }


def build_review(move_records: list[dict[str, Any]], *, game_result: str | None, pgn: str) -> dict[str, Any]:
    """根据逐步分析结果生成复盘摘要（不调用 LLM，确定性、可演示）。"""
    eval_curve = build_eval_curve(move_records)
    accuracy = compute_accuracy(move_records)
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
            "eval_curve": eval_curve,
            "accuracy": accuracy,
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
        f"本局共 {len(move_records)} 步/局面分析，结果：{game_result or '进行中/未知'}。",
        f"平均 AI 争议度 {round(avg_dg * 100)}%；触发辩论 {len(debates)} 次。",
    ]
    if accuracy.get("overall") is not None:
        narrative.insert(
            1,
            f"准确率 总评 {accuracy['overall']}%"
            + (f"（白 {accuracy['white']}% / 黑 {accuracy['black']}%）" if accuracy.get("white") is not None else "")
            + "。",
        )
    pos_only = [r for r in move_records if r.get("position_only") or (r.get("move") or {}).get("san") == "局面分析"]
    if pos_only:
        narrative.insert(
            1,
            f"含 {len(pos_only)} 次局面级 Council（路演 Demo / 识谱分析）。",
        )
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
        label = f"第 {d0.get('number')} 步 {d0.get('san')}" if d0.get("san") not in (None, "局面分析") else "局面分析"
        if d0.get("san") == "局面分析":
            label = "局面分析"
        narrative.append(
            f"最高戏剧性辩论出现在 {label}，"
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
        "eval_curve": eval_curve,
        "accuracy": accuracy,
    }
